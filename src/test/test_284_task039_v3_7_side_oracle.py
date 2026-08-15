from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from benchmarks.task039_v3_side_oracle import (
    _audit_explicit_f_action,
    _relative_vec_difference,
    audit_hybrid_operator_identity,
    build_research_independent_hybrid_reference,
    rebuild_hybrid_augmented_vector,
    run_exact_side_lu_oracle,
    select_current_full_fe_shard,
)
from mpi4py import MPI
from petsc4py import PETSc
from src.solvers.hybrid_fem_modal_augmented_direct import HybridAugmentedLayout
from src.test.test_241_task037b_hybrid_action_modal_schur import (
    _destroy_fixture,
    _matrix_from_dense,
    _tiny_fixture,
    _zero_research_components,
)
from src.solvers.static_local_schur_action import (
    materialize_research_explicit_fine_matrix,
)
from src.solvers.condensed_dtn import (
    ResearchExplicitDtnBlocks,
    condensed_rhs,
)


def _identity_matrix(size: int) -> PETSc.Mat:
    template = PETSc.Vec().createMPI((None, size))
    matrix = _matrix_from_dense(template, template, np.eye(size, dtype=np.complex128))
    template.destroy()
    return matrix


def test_select_current_rank_shard_is_path_and_sha_bound(tmp_path):
    manifest = tmp_path / "manifest.json"
    shard = tmp_path / "rank0000.jsonl"
    shard.write_bytes(b"rank-0")
    inventory = {
        "canonical": {
            "bottom.full_fe": {
                "manifest": {"path": str(manifest)},
                "shards": [
                    {
                        "rank": 0,
                        "filename": shard.name,
                        "file_sha256": __import__("hashlib")
                        .sha256(shard.read_bytes())
                        .hexdigest(),
                        "packet_count": 1,
                    }
                ],
            }
        }
    }
    selected = select_current_full_fe_shard(inventory, "bottom", 0)
    assert selected["path"] == str(shard.resolve())
    assert (
        selected["sha256"]
        == inventory["canonical"]["bottom.full_fe"]["shards"][0]["file_sha256"]
    )


def test_rebuild_vector_uses_current_owned_active_values(monkeypatch, tmp_path):
    comm = MPI.COMM_WORLD
    bottom_a = _identity_matrix(2)
    top_a = _identity_matrix(2)
    bottom = SimpleNamespace(
        A=bottom_a,
        global_size=2,
        V=object(),
        floquet_data=object(),
        n_external_aux=0,
        static_condensation=SimpleNamespace(
            condensed=SimpleNamespace(
                owned_active_rows=2,
                trace_constraints=SimpleNamespace(
                    owned_active_original_dofs=np.asarray([1, 3], dtype=np.int64)
                ),
            )
        ),
        local_mesh=SimpleNamespace(mesh=SimpleNamespace(comm=comm)),
    )
    top = SimpleNamespace(**{**bottom.__dict__, "A": top_a})
    layout = HybridAugmentedLayout.build(bottom, top, 2)
    fake_index_map = SimpleNamespace(
        size_local=4,
        local_to_global=lambda values: np.asarray(values, dtype=np.int64),
    )
    fake_field = SimpleNamespace(
        function_space=SimpleNamespace(
            dofmap=SimpleNamespace(index_map=fake_index_map, index_map_bs=1)
        ),
        x=SimpleNamespace(array=np.asarray([10, 20, 30, 40], dtype=np.complex128)),
    )
    monkeypatch.setattr(
        "benchmarks.task039_v3_side_oracle.read_canonical_packet_shard",
        lambda path, digest: [{"packet": index} for index in range(4)],
    )
    monkeypatch.setattr(
        "benchmarks.task039_v3_side_oracle.reconstruct_canonical_full_fe_function",
        lambda space, packets, floquet: fake_field,
    )
    manifest = tmp_path / "manifest.json"
    inventory = {
        "canonical": {
            f"{side}.full_fe": {
                "manifest": {"path": str(manifest)},
                "shards": [
                    {
                        "rank": 0,
                        "filename": "rank.jsonl",
                        "file_sha256": "a" * 64,
                        "packet_count": 4,
                    }
                ],
            }
            for side in ("bottom", "top")
        }
    }
    try:
        vector, audit = rebuild_hybrid_augmented_vector(
            inventory, bottom, top, layout, np.asarray([1 + 0j, 2 + 0j])
        )
        assert np.array_equal(vector.getArray(), np.asarray([20, 40, 20, 40, 1, 2]))
        assert audit["mapping_status"] == "canonical_full_fe_to_owned_active_trace"
        for side in ("bottom", "top"):
            assert audit["mapping_audit"][side] == {
                "shard_path": str((tmp_path / "rank.jsonl").resolve()),
                "sha256": "a" * 64,
                "declared_packet_count": 4,
                "actual_packet_count": 4,
                "owned_full_fe_rows": 4,
                "owned_active_rows": 2,
            }
        vector.destroy()
    finally:
        bottom_a.destroy()
        top_a.destroy()


def test_operator_identity_requires_blocks_rhs_and_isolated_inputs():
    fixture = _tiny_fixture()
    layout = fixture["layout"]
    dense = np.eye(layout.global_size, dtype=np.complex128)
    matrices = []
    vectors = []
    isolated = {}
    rhs_left = rhs_right = None
    try:
        template = layout.create_vector()
        assembled = _matrix_from_dense(template, template, dense)
        template.destroy()
        matrices.append(assembled)
        source = layout.create_vector()
        source.set(1.0)
        vectors.append(source)
        for label, block_slice in (
            ("bottom_only", layout.local_bottom_slice),
            ("top_only", layout.local_top_slice),
            ("modal_only", layout.local_modal_slice),
        ):
            vector = layout.create_vector()
            vector.set(0.0)
            vector.getArray()[block_slice] = 1.0
            isolated[label] = vector
            vectors.append(vector)
        rhs_left = layout.create_vector()
        rhs_right = layout.create_vector()
        rhs_left.set(1.0)
        rhs_right.set(1.0)
        report = audit_hybrid_operator_identity(
            assembled,
            assembled,
            layout,
            {"random_0": source},
            rhs_pairs={"physical_rhs": (rhs_left, rhs_right)},
            isolated_vectors=isolated,
        )
        assert report["pass"] is True
        assert report["rhs_equality"]["pass"] is True
        assert report["coupling_isolation"]["pass"] is True
        assert set(report["coupling_isolation"]) >= {
            "P_bottom",
            "P_top",
            "T_bottom",
            "T_top",
        }
        for key in ("P_bottom", "P_top", "T_bottom", "T_top"):
            assert set(report["coupling_isolation"][key]) >= {
                "relative_error",
                "reference_norm",
                "limit",
                "pass",
            }

        bad_dense = dense.copy()
        modal_start = int(layout.modal_global_start)
        bad_dense[modal_start, modal_start] = 1.1
        template = layout.create_vector()
        bad_matrix = _matrix_from_dense(template, template, bad_dense)
        template.destroy()
        matrices.append(bad_matrix)
        bad_report = audit_hybrid_operator_identity(
            assembled,
            bad_matrix,
            layout,
            {"random_0": source},
            rhs_pairs={"physical_rhs": (rhs_left, rhs_right)},
            isolated_vectors=isolated,
        )
        assert bad_report["pass"] is False
        assert bad_report["vectors"]["random_0"]["blocks"]["modal"]["pass"] is False
    finally:
        if rhs_left is not None:
            rhs_left.destroy()
        if rhs_right is not None:
            rhs_right.destroy()
        for vector in vectors:
            vector.destroy()
        for matrix in matrices:
            matrix.destroy()
        _destroy_fixture(fixture)


def test_research_explicit_f_and_oracle_lifecycle(monkeypatch):
    fixture = _tiny_fixture()
    condensed = SimpleNamespace(
        active_rows=2,
        owned_active_rows=2,
        comm=MPI.COMM_WORLD,
        retained_local_schur_by_class={"tiny": np.eye(2, dtype=np.complex128)},
    )
    system = SimpleNamespace(
        static_condensation=SimpleNamespace(condensed=condensed),
        fine_action=None,
    )
    expected_template = PETSc.Vec().createMPI((None, 2), comm=MPI.COMM_WORLD)
    expected = _matrix_from_dense(
        expected_template,
        expected_template,
        np.diag([2.0 + 0.1j, 2.4 - 0.2j]),
    )
    expected_template.destroy()
    system.fine_action = expected
    monkeypatch.setattr(
        "src.solvers.static_local_schur_action.iter_owned_constrained_schur_contributions",
        lambda _condensed: iter(
            [
                (
                    0,
                    np.asarray([0, 1], dtype=PETSc.IntType),
                    np.diag([2.0 + 0.1j, 2.4 - 0.2j]),
                )
            ]
        ),
    )
    explicit = materialize_research_explicit_fine_matrix(condensed)
    try:
        assert _audit_explicit_f_action(explicit, expected)["pass"] is True
    finally:
        explicit.destroy()
        expected.destroy()

    components = []
    for side in (fixture["bottom"], fixture["top"]):
        side.fine_action = side.A
        side.static_condensation = SimpleNamespace(condensed=condensed)
        side.external_modes = [object(), object()]
        component = _zero_research_components(fixture, side)
        row = side.A.createVecLeft()
        modal = component.H.createVecRight()
        component.C.destroy()
        component.C = _matrix_from_dense(
            row,
            modal,
            np.asarray(
                [[0.15 + 0.01j, 0.0], [0.0, 0.12 - 0.02j], [0.03, 0.0], [0.0, 0.02]],
                dtype=np.complex128,
            ),
        )
        row.destroy()
        modal.destroy()
        component.b_fe = side.A.createVecLeft()
        component.b_fe.set(0.25 + 0.1j)
        component.b_aux = component.H.createVecRight()
        if MPI.COMM_WORLD.rank == MPI.COMM_WORLD.size - 1:
            component.b_aux.getArray()[:] = np.asarray(
                [0.4 - 0.1j, -0.2 + 0.05j],
                dtype=PETSc.ScalarType,
            )
        component.b_aux.assemble()
        expected_rhs = condensed_rhs(
            SimpleNamespace(
                b_fe=component.b_fe,
                b_aux=component.b_aux,
                C=component.C,
                D=component.D,
                H=component.H,
            )
        )
        side.b.getArray()[:] = expected_rhs.getArray(readonly=True)
        expected_rhs.destroy()
        side.blocks = component
        components.append(component)

    def fake_materialize(_condensed):
        template = fixture["bottom"].A.createVecRight()
        matrix = _matrix_from_dense(
            template,
            template,
            np.diag(fixture["diagonal"]),
        )
        template.destroy()
        return matrix

    monkeypatch.setattr(
        "benchmarks.task039_v3_side_oracle.materialize_research_explicit_fine_matrix",
        fake_materialize,
    )

    def fake_materialize_dtn(blocks):
        return ResearchExplicitDtnBlocks(
            blocks.C.copy(),
            blocks.D.copy(),
            blocks.H.copy(),
            {"research_only": True, "synthetic": True},
        )

    monkeypatch.setattr(
        "benchmarks.task039_v3_side_oracle.materialize_research_explicit_dtn_blocks",
        fake_materialize_dtn,
    )
    condensed_rhs_calls = []
    real_condensed_rhs = condensed_rhs

    def counting_condensed_rhs(blocks):
        condensed_rhs_calls.append(True)
        return real_condensed_rhs(blocks)

    monkeypatch.setattr(
        "benchmarks.task039_v3_side_oracle.condensed_rhs",
        counting_condensed_rhs,
    )
    rhs = fixture["layout"].create_vector()
    rhs.set(1.0)
    captured = {}
    reference = None
    try:
        reference = build_research_independent_hybrid_reference(
            fixture["bottom"], fixture["top"], fixture["coupling"]
        )
        assert len(condensed_rhs_calls) == 2
        assert _relative_vec_difference(reference.bottom.b, components[0].b_fe) > 1.0e-6
        assert (
            _relative_vec_difference(reference.bottom.b, fixture["bottom"].b) <= 1.0e-12
        )
        assert _relative_vec_difference(reference.top.b, fixture["top"].b) <= 1.0e-12
        assert reference.bottom.b is not fixture["bottom"].b
        report = run_exact_side_lu_oracle(
            fixture["layout"],
            fixture["bottom"],
            fixture["top"],
            fixture["coupling"],
            rhs,
            reference=reference,
            factor_solver_type=None,
            solution_consumer=lambda solution, _report: captured.setdefault(
                "solution", np.asarray(solution.getArray()).copy()
            ),
        )
        assert report["pass"] is True
        assert report["reference_ownership"] == "borrowed"
        assert report["lifecycle"]["borrowed_reference_destroyed_by_oracle"] is False
        assert report["solution_handoff"] == "callback_consumed_before_cleanup"
        assert report["inventory"]["bottom_direct_factor_count"] == 1
        assert report["inventory"]["top_direct_factor_count"] == 1
        assert report["inventory"]["bottom_ilu_factor_count"] == 0
        assert report["inventory"]["top_ilu_factor_count"] == 0
        assert report["inventory"]["borrowed_ilu_factor_count"] == 0
        assert report["external_mode_count"] == {"bottom": 2, "top": 2}
        assert report["lifecycle"]["solution_consumer_synchronous"] is True
        assert captured["solution"].shape == (fixture["layout"].local_size,)
    finally:
        if reference is not None:
            reference.destroy()
        rhs.destroy()
        for component in components:
            component.b_aux.destroy()
            component.b_fe.destroy()
            component.C.destroy()
            component.D.destroy()
            component.H.destroy()
        _destroy_fixture(fixture)
