from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pytest

from benchmarks.task43_hp_adaptivity import h100_anchor
from benchmarks.task43_hp_adaptivity import r10_h67_diagnostic
from benchmarks.task43_hp_adaptivity import round1_candidates


CONTRACT = (
    Path(__file__).resolve().parents[2]
    / "docs/task43_hp_adaptivity/outcomes/records/v21_r10_h67_contract.json"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _candidate_fixture(tmp_path: Path, *, diagnostic_status: str = "REJECTED"):
    acceptance = tmp_path / "acceptance.json"
    acceptance.write_text('{"schema":"fixture"}\n', encoding="utf-8")
    acceptance_sha = _sha256(acceptance)
    plan = {
        "cell_interior_degree": 6,
        "trace_degree": 6,
        "variable_trace_from_cell_degrees": True,
        "cell_interior_degrees": [{"degree": 6}],
        "expected_forest": {"leaf_cell_count": 1},
        "selection_enabled": False,
        "transition_written": False,
        "task43_candidate": {
            "candidate_id": "v21_r10_h67",
            "action": "h_refine",
            "provenance": {
                "accepted_state": {
                    "candidate_id": "round9_p_up",
                    "selection_status": "ACCEPTED",
                    "selection_sha256": "a" * 64,
                },
                "diagnostic_parent": {
                    "candidate_id": "round10_p_up",
                    "selection_status": diagnostic_status,
                    "record_sha256": "b" * 64,
                    "storage_sha256": "c" * 64,
                },
                "acceptance_contract_sha256": acceptance_sha,
                "selection_enabled": False,
                "transition_written": False,
            },
        },
    }
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan, sort_keys=True) + "\n", encoding="utf-8")
    binding = {
        "space_plan_path": str(plan_path.resolve()),
        "space_plan_sha256": _sha256(plan_path),
        "acceptance_contract_path": str(acceptance.resolve()),
        "acceptance_contract_sha256": acceptance_sha,
        "contract_sha256": "d" * 64,
    }
    return plan_path, acceptance, binding


def _space_products(tmp_path: Path) -> dict:
    products = {}
    roles = (
        "space_plan",
        "space_audit",
        "space_bundle",
        "space_terminal",
        "space_watchdog",
        "space_launcher",
        "space_root_audit",
    )
    for role in roles:
        path = tmp_path / f"{role}.json"
        payload = (
            {
                "status": "QUALIFIED_FOR_F1",
                "checks": {
                    "source": True,
                    "input": True,
                    "trace": True,
                    "resource": True,
                    "cleanup": True,
                },
                "formal_admission": {"pass": True},
            }
            if role == "space_root_audit"
            else {"role": role}
        )
        path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        products[role] = {"path": str(path.resolve()), "sha256": _sha256(path)}
    return {"space_products": products}


def test_00_v21_worker_runtime_identity_is_saved():
    """The targeted worker records its real watchdog/ABI identity once per run."""
    stage = os.environ.get("TASK43_V21_STAGE")
    if stage not in {"T1", "T2", "T3"}:
        pytest.skip("runtime identity is only recorded inside a V21 targeted slot")
    root_text = os.environ.get("TASK43_V21_RUN_ROOT")
    assert root_text
    root = Path(root_text)
    runtime = h100_anchor._check_v11_runtime_envelope(h100_anchor.MPI.COMM_WORLD)
    identity = runtime["v11_watchdog_worker_identity"]
    assert identity["worker_pid"] == os.getpid()
    assert all(item["cpu_list"] == [1] for item in identity["worker_tid_affinities"])
    path = root / "runtime_identity.json"
    assert not path.exists()
    h100_anchor.write_atomic_json(
        path,
        {
            "schema": "task43.v21.targeted-runtime-identity.v1",
            "stage": stage,
            "run_root": str(root.resolve()),
            "runtime": runtime,
        },
    )


def test_01_contract_reader_accepts_frozen_f1_root():
    contract, digest = r10_h67_diagnostic.load_contract(
        CONTRACT,
        stage="F1",
        stage_root=(
            r10_h67_diagnostic.ROOT
            / "benchmarks/artifacts/task43/v21_r10_h67/formal/R10_H67_attempt1"
        ),
        verify_inputs=False,
    )
    assert contract["candidate"]["global_cell_id"] == 67
    assert contract["candidate"]["forest_root"] == 127
    assert len(digest) == 64


def test_02_contract_reader_rejects_another_unique_root():
    with pytest.raises(ValueError, match="unique contract root"):
        r10_h67_diagnostic.load_contract(
            CONTRACT,
            stage="F1",
            stage_root=CONTRACT.parent,
            verify_inputs=False,
        )
    with pytest.raises(ValueError, match="unique contract root"):
        r10_h67_diagnostic.main(
            [
                "--contract",
                str(CONTRACT),
                "--stage",
                "F1",
                "--stage-root",
                str(CONTRACT.parent),
            ]
        )


def test_04_candidate_reader_binds_accepted9_and_rejected_r10(tmp_path):
    plan_path, acceptance, binding = _candidate_fixture(tmp_path)
    plan, digest, identity = h100_anchor._validate_v21_h67_candidate_inputs(
        candidate_plan_path=plan_path,
        candidate_id="v21_r10_h67",
        acceptance_contract_path=acceptance,
        v21_source_binding=binding,
    )
    assert digest == binding["space_plan_sha256"]
    assert identity["accepted_state_selection_status"] == "ACCEPTED"
    assert identity["parent_selection_status"] == "REJECTED"
    assert plan["task43_candidate"]["action"] == "h_refine"


def test_05_candidate_reader_rejects_promoting_rejected_r10(tmp_path):
    plan_path, acceptance, binding = _candidate_fixture(
        tmp_path, diagnostic_status="ACCEPTED"
    )
    binding["space_plan_sha256"] = _sha256(plan_path)
    with pytest.raises(ValueError, match="preserve accepted9 and rejected R10"):
        h100_anchor._validate_v21_h67_candidate_inputs(
            candidate_plan_path=plan_path,
            candidate_id="v21_r10_h67",
            acceptance_contract_path=acceptance,
            v21_source_binding=binding,
        )


def test_06_actual_s_builder_and_post_audit_gate_h67_with_p6_closure(
    tmp_path, monkeypatch
):
    """Use real forest/plan/audit logic; substitute only the costly FE authority."""
    from types import SimpleNamespace
    from src.adaptivity.stage4_local_h import _forest_expectation

    cfg = h100_anchor._h100_config(
        kind="empty_h_active_p3", case_name="v21_s_builder_fixture", geometry_profile="initial_180"
    )
    parent_forest = round1_candidates._build_forest(
        cfg,
        comm_size=1,
        marked_root_boxes=(),
        maximum_level=1,
        allow_no_refinement=True,
    )
    requested_box = (16.5, 10.0, 90.0, 33.5, 15.0, 120.0)
    matching_roots = [
        index
        for index, box in enumerate(parent_forest.root_boxes)
        if tuple(map(float, box)) == requested_box
    ]
    assert len(parent_forest.root_boxes) == 180
    assert matching_roots == [127]
    fixture_vertices = np.asarray(
        [
            (x, y, z)
            for box in parent_forest.root_boxes
            for x in (box[0], box[3])
            for y in (box[1], box[4])
            for z in (box[2], box[5])
        ],
        dtype=np.float64,
    )
    fixture_dofmap = np.arange(180 * 8, dtype=np.int64).reshape(180, 8)
    fixture_ids = np.arange(180, dtype=np.int64)
    fixture_ids[67], fixture_ids[127] = fixture_ids[127], fixture_ids[67]
    mapped_box, mapped_roots = round1_candidates._v21_h67_parent_seed_mapping(
        fixture_ids, fixture_dofmap, fixture_vertices, parent_forest.root_boxes
    )
    assert mapped_box == requested_box and mapped_roots == [127]
    with pytest.raises(ValueError, match="global67 box"):
        round1_candidates._v21_h67_parent_seed_mapping(
            np.arange(180), fixture_dofmap, fixture_vertices, parent_forest.root_boxes
        )

    candidate_forest = round1_candidates._build_forest(
        cfg,
        comm_size=1,
        marked_root_boxes=(requested_box,),
        maximum_level=1,
        allow_no_refinement=False,
    )
    parent_degree_by_box = {tuple(map(float, box)): 6 for box in parent_forest.root_boxes}
    leaf_degrees = {leaf.box: parent_degree_by_box[tuple(map(float, parent_forest.root_boxes[leaf.key.root]))] for leaf in candidate_forest.leaves}
    provenance = {
        "requested_global_cell_id": 67,
        "requested_forest_root": 127,
        "parent_candidate_id": "round10_p_up",
        "parent_selection_status": "REJECTED",
        "accepted_candidate_id": "round9_p_up",
        "accepted_selection_status": "ACCEPTED",
    }
    plan = round1_candidates.stage4_local_h_refinement_plan_payload(
        cfg,
        (requested_box,),
        comm_size=1,
        trace_degree=6,
        cell_interior_degree=6,
        provenance=provenance,
        cell_interior_degree_overrides=leaf_degrees,
        variable_trace_from_cell_degrees=True,
        allow_no_refinement=False,
    )
    plan["task43_candidate"] = {
        "candidate_id": "v21_r10_h67",
        "action": "h_refine",
        "provenance": provenance,
    }
    plan["selection_enabled"] = False
    plan["transition_written"] = False
    plan_path = tmp_path / "plans/v21_r10_h67.json"
    plan_path.parent.mkdir()
    plan_path.write_text(json.dumps(plan, sort_keys=True) + "\n", encoding="utf-8")

    split_count = (len(candidate_forest.leaves) - len(candidate_forest.root_boxes)) // 7
    assert split_count >= 1
    interior_rows = 81000 + 3150 * split_count
    trace_rows = 37800
    digest = "5" * 64
    leaf_digest = str(candidate_forest.audit["leaf_catalog_sha256"])
    root_digest = _forest_expectation(candidate_forest)["root_catalog_sha256"]
    context_audit = {
        "root_cell_count": len(candidate_forest.root_boxes),
        "leaf_cell_count": len(candidate_forest.leaves),
        "hanging_patch_count": len(candidate_forest.hanging_faces),
        "forest": {
            "closure_split_counts": dict(candidate_forest.audit["closure_split_counts"]),
            "leaf_catalog_sha256": leaf_digest,
        },
    }
    coordinates = np.asarray(
        [[x, y, z] for x in (0.0, 1.0) for y in (0.0, 1.0) for z in (0.0, 1.0)],
        dtype=np.float64,
    )
    mesh = SimpleNamespace(
        geometry=SimpleNamespace(x=coordinates, dofmap=np.arange(8, dtype=np.int32).reshape(1, 8))
    )
    mesh_data = SimpleNamespace(
        mesh=mesh,
        mesh_cell_type_resolved="hexahedron",
        local_h_context=SimpleNamespace(audit=context_audit, forest=candidate_forest),
    )
    entity_map = SimpleNamespace(
        owned_cells=(),
        active_cell_interior_rows=interior_rows,
        active_rows=interior_rows + trace_rows,
        uniform_p6_rows=interior_rows + trace_rows,
        uniform_p6_trace_rows=trace_rows,
        audit={"full_p6_global_matrix_constructed": False},
    )
    degree_plan = SimpleNamespace(
        entity_map=entity_map,
        audit={
            "cell_degree_counts": {"p6": len(candidate_forest.leaves)},
            "cell_degree_plan_sha256": digest,
            "runtime_global_entity_degree_sha256": "7" * 64,
            "mesh_cell_box_catalog_sha256": "8" * 64,
            "minimum_trace_degree": 6,
            "pass": True,
        },
    )
    authority = SimpleNamespace(
        audit={
            "pass": True,
            "physical_trace": {"trace_degree_values": [6]},
            "trace_constraints": {
                "hanging_slave_rows": 0,
                "hanging_or_floquet_slave_rows_globally_numbered": False,
            },
            "raw_broken_active_fe_dofs": 300000,
            "active_fe_dof_gate_policy": "fixture_authority",
            "active_fe_dof_gate_limit": None,
            "active_fe_dof_gate_pass": True,
        },
        degree_plan=degree_plan,
        trace_constraints=SimpleNamespace(independent_trace_rows=trace_rows),
    )
    monkeypatch.setattr(
        round1_candidates,
        "build_stage4_local_h_mesh_data",
        lambda *_args, **_kwargs: mesh_data,
    )
    monkeypatch.setattr(
        round1_candidates,
        "build_stage4_local_h_reduction_authority",
        lambda *_args, **_kwargs: authority,
    )
    audit = round1_candidates._audit_plan(
        cfg,
        plan_path=plan_path,
        candidate_id="v21_r10_h67",
        comm=round1_candidates.MPI.COMM_WORLD,
        parent_independent_fe_dofs=118800,
        parent_root_degree_by_box=parent_degree_by_box,
        audit_parent_transfer=False,
    )
    source_binding = {
        "space_forest": {"actual_leaf_cell_count": len(candidate_forest.leaves)},
        "space_root_catalog_sha256": root_digest,
        "space_leaf_catalog_sha256": leaf_digest,
        "space_plan_sha256": audit["plan_sha256"],
    }
    actual_mesh_identity = {
        "root_catalog_sha256": root_digest,
        "leaf_catalog_sha256": leaf_digest,
    }
    post_audit = h100_anchor._v21_h67_actual_space_audit(
        plan=plan,
        plan_identity={
            "root_cell_count": audit["forest"]["root_cell_count"],
            "leaf_cell_count": audit["forest"]["actual_leaf_cell_count"],
            "marked_root_count": audit["forest"]["requested_h_root_splits"],
            "root_catalog_sha256": root_digest,
            "leaf_catalog_sha256": leaf_digest,
            "plan_sha256": audit["plan_sha256"],
        },
        actual_mesh_identity=actual_mesh_identity,
        source_binding=source_binding,
    )
    actual_fe = audit["dofs"]["independent_active_fe_dofs"]
    assert post_audit["pass"] is True
    assert audit["space_authority_detail"]["requested_root_ids"] == [127]
    assert audit["space_authority_detail"]["forced_closure_root_ids"]
    assert audit["forest"]["actual_one_level_root_splits"] == split_count
    assert audit["degrees"]["cell_interior_histogram"] == {"p6": len(candidate_forest.leaves)}
    assert audit["space_authority_detail"]["all_actual_leaves_inherit_parent_degree"] is True
    assert actual_fe == trace_rows + interior_rows
    assert 118800 < actual_fe < 237600


def test_08_s_product_reader_requires_all_seven_qualified_artifacts(tmp_path):
    binding = _space_products(tmp_path)
    verified = h100_anchor._verify_v21_h67_space_products(binding)
    assert set(verified) == {
        "space_plan",
        "space_audit",
        "space_bundle",
        "space_terminal",
        "space_watchdog",
        "space_launcher",
        "space_root_audit",
    }
    binding["space_products"].pop("space_terminal")
    with pytest.raises(ValueError, match="exact seven S products"):
        h100_anchor._verify_v21_h67_space_products(binding)


def test_09_s_product_reader_rejects_changed_product_bytes(tmp_path):
    binding = _space_products(tmp_path)
    Path(binding["space_products"]["space_audit"]["path"]).write_text(
        "changed\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="changed during F"):
        h100_anchor._verify_v21_h67_space_products(binding)


@pytest.mark.parametrize("fail_after_writer", [False, True])
def test_12_v21_f_main_reaches_real_observer_writer_and_terminal(
    tmp_path, monkeypatch, fail_after_writer
):
    """Drive V21's real CLI/main, raw gates, observer, shared writer, and terminal."""
    from types import SimpleNamespace

    from benchmarks.task43_hp_adaptivity import compare_v2_endpoints
    from benchmarks.task43_hp_adaptivity import candidate_checkpoints
    from src.postprocessing import rta_3d
    from src.solvers import common_3d_case_flow
    from src.test.test_task43_v11_scientific_restart import (
        _ObserverMatrix,
        _ObserverVector,
        _raw_gate_arguments,
        _raw_vectors,
    )

    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    contract_sha = _sha256(CONTRACT)
    s_root = tmp_path / "completed_s"
    plan_path = s_root / "plan_output/plans/v21_r10_h67.json"
    plan_path.parent.mkdir(parents=True)
    from src.adaptivity.stage4_local_h import _forest_expectation

    cfg = h100_anchor._h100_config(
        kind="empty_h_active_p3",
        case_name="v21_h67_main_fixture",
        geometry_profile="initial_180",
    )
    parent_forest = round1_candidates._build_forest(
        cfg,
        comm_size=1,
        marked_root_boxes=(),
        maximum_level=1,
        allow_no_refinement=True,
    )
    requested_box = (16.5, 10.0, 90.0, 33.5, 15.0, 120.0)
    candidate_forest = round1_candidates._build_forest(
        cfg,
        comm_size=1,
        marked_root_boxes=(requested_box,),
        maximum_level=1,
        allow_no_refinement=False,
    )
    parent_degree_by_box = {
        tuple(map(float, box)): 6 for box in parent_forest.root_boxes
    }
    leaf_degrees = {
        leaf.box: parent_degree_by_box[
            tuple(map(float, parent_forest.root_boxes[leaf.key.root]))
        ]
        for leaf in candidate_forest.leaves
    }
    acceptance = (
        r10_h67_diagnostic.ROOT
        / contract["inputs"]["round1_acceptance_contract"]["path"]
    )
    acceptance_sha = _sha256(acceptance)
    provenance = {
        "accepted_state": {
            "candidate_id": "round9_p_up",
            "selection_status": "ACCEPTED",
            "selection_sha256": "3" * 64,
        },
        "diagnostic_parent": {
            "candidate_id": "round10_p_up",
            "selection_status": "REJECTED",
            "record_sha256": "4" * 64,
            "storage_sha256": "5" * 64,
        },
        "requested_h_seed": {
            "global_cell_id": 67,
            "forest_root_index": 127,
            "box_nm": list(requested_box),
            "split": "one_level_1_to_8",
            "maximum_level": 1,
        },
        "acceptance_contract_sha256": acceptance_sha,
        "selection_enabled": False,
        "transition_written": False,
    }
    plan = round1_candidates.stage4_local_h_refinement_plan_payload(
        cfg,
        (requested_box,),
        comm_size=1,
        trace_degree=6,
        cell_interior_degree=6,
        provenance=provenance,
        cell_interior_degree_overrides=leaf_degrees,
        variable_trace_from_cell_degrees=True,
        allow_no_refinement=False,
    )
    plan["task43_candidate"] = {
        "candidate_id": "v21_r10_h67",
        "action": "h_refine",
        "action_description": "one-level H67 split with inherited p6",
        "provenance": provenance,
    }
    plan["selection_enabled"] = False
    plan["transition_written"] = False
    leaf_count = len(candidate_forest.leaves)
    root_catalog_sha = _forest_expectation(candidate_forest)["root_catalog_sha256"]
    leaf_catalog_sha = str(candidate_forest.audit["leaf_catalog_sha256"])
    plan_path.write_text(json.dumps(plan, sort_keys=True) + "\n", encoding="utf-8")

    products_root = tmp_path / "space_products"
    products_root.mkdir()
    space_products = _space_products(products_root)
    plan_product = space_products["space_products"]["space_plan"]
    Path(plan_product["path"]).write_bytes(plan_path.read_bytes())
    plan_product["sha256"] = _sha256(Path(plan_product["path"]))
    space_binding = {
        "stage": "F1",
        "contract_path": str(CONTRACT.resolve()),
        "contract_sha256": contract_sha,
        "acceptance_contract_path": str(acceptance.resolve()),
        "acceptance_contract_sha256": acceptance_sha,
        "run_root": str((tmp_path / "F1/run").resolve()),
        "space_root": str(s_root.resolve()),
        "space_plan_path": str(plan_path.resolve()),
        "space_plan_sha256": _sha256(plan_path),
        "space_actual_independent_fe_dofs": 118801,
        "space_forest": {
            "root_cell_count": 180,
            "actual_leaf_cell_count": leaf_count,
            "root_catalog_sha256": root_catalog_sha,
            "leaf_catalog_sha256": leaf_catalog_sha,
        },
        "space_root_catalog_sha256": root_catalog_sha,
        "space_leaf_catalog_sha256": leaf_catalog_sha,
        "space_products": space_products["space_products"],
        "space_root_audit": json.loads(
            Path(space_products["space_products"]["space_root_audit"]["path"])
            .read_text(encoding="utf-8")
        ),
        "selection_enabled": False,
        "transition_written": False,
    }
    source_before = {"fixture_source": "a" * 64}
    input_before = {"fixture_input": "b" * 64}

    def load_fixture_contract(_path, *, stage, stage_root):
        assert stage == "F1"
        assert Path(stage_root) == tmp_path / "F1"
        return contract, contract_sha

    monkeypatch.setattr(r10_h67_diagnostic, "load_contract", load_fixture_contract)
    monkeypatch.setattr(r10_h67_diagnostic, "slot_root", lambda _c, stage: s_root if stage == "S" else tmp_path / stage)
    monkeypatch.setattr(r10_h67_diagnostic, "source_snapshot", lambda _c: dict(source_before))
    monkeypatch.setattr(r10_h67_diagnostic, "input_snapshot", lambda _c: dict(input_before))
    monkeypatch.setattr(
        r10_h67_diagnostic,
        "require_snapshot_equal",
        lambda _c, *, source_before, input_before: (
            dict(source_before),
            dict(input_before),
        ),
    )
    monkeypatch.setattr(
        h100_anchor,
        "_load_v21_h67_f_context",
        lambda **_kwargs: (
            contract,
            contract_sha,
            space_binding,
            dict(source_before),
            dict(input_before),
        ),
    )
    real_watchdog_identity = h100_anchor._require_v11_watchdog_worker_identity
    phase_checks = []

    def allow_reused_fixture_phase(*, require_unused_phase_file=True, expected_identity=None):
        # The success/failure parameter cases share a T worker. Preserve all
        # real identity checks; only failure-case phase-marker reuse is allowed.
        phase_checks.append(
            require_unused_phase_file and not fail_after_writer
        )
        return real_watchdog_identity(
            require_unused_phase_file=(require_unused_phase_file and not fail_after_writer),
            expected_identity=expected_identity,
        )

    monkeypatch.setattr(
        h100_anchor,
        "_require_v11_watchdog_worker_identity",
        allow_reused_fixture_phase,
    )

    class _Topology:
        dim = 3

        def index_map(self, _dimension):
            return SimpleNamespace(size_global=leaf_count)

        def create_connectivity(self, *_args):
            return None

    mesh_data = SimpleNamespace(
        mesh=SimpleNamespace(topology=_Topology()),
        local_h_context=SimpleNamespace(
            audit={
                "status": "passed",
                "pass": True,
                "root_cell_count": 180,
                "leaf_cell_count": leaf_count,
                "hanging_patch_count": len(candidate_forest.hanging_faces),
                "cell_interior_degree_counts": {"p6": leaf_count},
                "variable_trace_from_cell_degrees": True,
                "allow_no_refinement": False,
                "forest": {
                    "closure_split_counts": dict(
                        candidate_forest.audit["closure_split_counts"]
                    ),
                    "leaf_catalog_sha256": leaf_catalog_sha,
                },
            },
            forest=candidate_forest,
        ),
    )
    axes = tuple(np.asarray([0.0, 1.0], dtype=np.float64) for _ in range(3))
    monkeypatch.setattr(h100_anchor, "build_airbox_mesh_3d", lambda *_a, **_k: mesh_data)
    monkeypatch.setattr(h100_anchor, "build_stage4_local_h_mesh_data", lambda *_a, **_k: mesh_data)
    monkeypatch.setattr(h100_anchor, "_mesh_axes", lambda *_a, **_k: axes)
    actual_mesh = {
        "root_catalog_sha256": root_catalog_sha,
        "leaf_catalog_sha256": leaf_catalog_sha,
        "closure_split_counts": dict(candidate_forest.audit["closure_split_counts"]),
        "hanging_patch_count": len(candidate_forest.hanging_faces),
        "mesh_box_catalog_sha256": "6" * 64,
    }
    monkeypatch.setattr(h100_anchor, "_assert_mesh_profile", lambda *_a, **_k: actual_mesh)
    monkeypatch.setattr(
        h100_anchor,
        "resolve_stage4_full3d_assembly_backend",
        lambda *_a, **_k: {"actual": h100_anchor.ASSEMBLY_TIME_VARIABLE_P_CONDENSED_BACKEND},
    )

    active_interior_rows = 118800
    independent_fe_dofs = active_interior_rows + 1
    active_full_rows = active_interior_rows + 2
    vectors = _raw_vectors()
    vectors["independent_A6_independent_active_residual_cell_interior"] = np.zeros(
        active_interior_rows, dtype=np.complex128
    )
    vectors["independent_A6_independent_active_rhs_cell_interior"] = np.ones(
        active_interior_rows, dtype=np.complex128
    )
    full_rhs = np.zeros(active_full_rows, dtype=np.complex128)
    full_rhs[-1] = 1.0
    full_solution = np.zeros(active_full_rows, dtype=np.complex128)
    interior_residual = np.zeros(active_full_rows, dtype=np.complex128)
    vectors["full_active_active_full_rhs"] = full_rhs
    vectors["full_active_active_full_solution"] = full_solution
    vectors["full_active_eliminated_active_interior_residual"] = interior_residual
    vectors["recovered_active_full_rhs_owned"] = full_rhs.copy()
    vectors["recovered_active_full_solution_owned"] = full_solution.copy()
    vectors["returned_trace_dtn_b_minus_Ax"] = np.zeros(613, dtype=np.complex128)
    vectors["full_active_reduced_trace_dtn_residual_Ax_minus_b_owned"] = np.zeros(
        613, dtype=np.complex128
    )
    vectors["full_active_reduced_trace_dtn_residual_trace_metric_action"] = np.zeros(
        1, dtype=np.complex128
    )
    vectors["full_active_reduced_trace_dtn_rhs_trace_metric_action"] = np.ones(
        1, dtype=np.complex128
    )
    vectors["normal_before_normal_correction_residual_b_minus_Ax"] = np.ones(
        613, dtype=np.complex128
    )
    vectors["normal_after_normal_correction_residual_b_minus_Ax"] = np.zeros(
        613, dtype=np.complex128
    )
    a6_raw = {
        name.removeprefix("independent_A6_"): value
        for name, value in vectors.items()
        if name.startswith("independent_A6_")
    }
    full_raw = {
        name.removeprefix("full_active_"): value
        for name, value in vectors.items()
        if name.startswith("full_active_")
    }
    normal_vectors = {
        name.removeprefix("normal_"): value
        for name, value in vectors.items()
        if name.startswith("normal_")
    }
    storage_arrays = {
        "recovered_p6_local_coefficients": np.asarray([1.0 + 0.0j], dtype=np.complex128),
        "recovered_p6_owned_coefficients": np.asarray([1.0 + 0.0j], dtype=np.complex128),
        "mesh_geometry_coordinates_nm": np.zeros((8, 3), dtype=np.float64),
        "mesh_geometry_dofmap": np.arange(8, dtype=np.int32).reshape(1, 8),
        "mesh_owned_cell_global_ids": np.asarray([127], dtype=np.int64),
        "mesh_cell_vertex_dofmap": np.arange(8, dtype=np.int32).reshape(1, 8),
        "p6_function_space_dofmap": np.arange(8, dtype=np.int32).reshape(1, 8),
        "p6_owned_global_dof_block_ids": np.asarray([0], dtype=np.int64),
        "p6_ghost_global_dof_block_ids": np.asarray([], dtype=np.int64),
        "active_full_solution_owned": full_solution.copy(),
        "active_full_rhs_owned": full_rhs.copy(),
    }
    mesh_order_sha = h100_anchor._sha256_json(
        {
            name: h100_anchor._array_identity(storage_arrays[name])
            for name in (
                "mesh_geometry_coordinates_nm",
                "mesh_geometry_dofmap",
                "mesh_owned_cell_global_ids",
                "mesh_cell_vertex_dofmap",
                "p6_function_space_dofmap",
                "p6_owned_global_dof_block_ids",
                "p6_ghost_global_dof_block_ids",
            )
        }
    )
    storage_metadata = {
        "active_degree_plan_sha256": "7" * 64,
        "mesh_and_dof_order_sha256": mesh_order_sha,
        "independent_active_fe_dofs": independent_fe_dofs,
        "active_rows": active_full_rows,
        "active_trace_rows": 1,
        "active_cell_interior_rows": active_interior_rows,
        "independent_trace_rows": 1,
        "active_cell_degree_counts": {"p6": leaf_count},
        "active_fe_dof_gate_pass": True,
        "degree_plan_pass": True,
        "trace_constraints_pass": True,
        "trace_constraints_status": "passed",
        "active_fe_dof_gate_policy": "fixture",
        "active_fe_dof_gate_limit": None,
    }
    monkeypatch.setattr(h100_anchor, "_active_solution_storage", lambda _view: (storage_arrays, storage_metadata))
    monkeypatch.setattr(
        h100_anchor,
        "compute_stage4_independent_active_action",
        lambda *_a, **_k: {
            "finite": True,
            "relative_residual": 0.0,
            "rows": {"independent_trace": 1, "active_cell_interior": active_interior_rows, "modal_lower": 612},
            "full_solver_gauge_residual": {
                "finite": True,
                "relative_to_independent_rhs": 0.0,
            },
            "raw_vectors": dict(a6_raw),
            "raw_vector_scope": {
                "trace_rows": 1,
                "active_interior_rows": active_interior_rows,
                "modal_lower_rows": 612,
            },
        },
    )
    monkeypatch.setattr(
        h100_anchor,
        "_field_capture",
        lambda *_a, **_k: {
            "axes_nm": {"x": [0.0, 1.0], "y": [0.0, 1.0], "z": [0.0, 1.0]},
            "mesh_identity": {"global_cells": leaf_count},
            "representation": {"fixture": "cell_local_vector"},
            "samples": {},
        },
    )
    monkeypatch.setattr(h100_anchor, "_log_stage", lambda *_a, **_k: None)

    mode_cfg = h100_anchor._h100_config(
        kind="empty_h_active_p3", case_name="v21_h67_main_fixture", geometry_profile="initial_180"
    )
    modes = h100_anchor.outgoing_port_modes_3d(mode_cfg)
    rows = [
        {
            "side": str(mode.side),
            "m": int(mode.m),
            "n": int(mode.n),
            "polarization": str(mode.polarization),
            "outgoing_amplitude_at_boundary": [0.0, 0.0],
            "power_carrying": bool(mode.propagating),
            "power_ratio": 0.0,
            "R": 0.0,
            "T": 0.0,
        }
        for mode in modes
    ]

    class _Integral:
        def __init__(self, metadata):
            self._metadata = metadata

        def integral_type(self):
            return "cell"

        def subdomain_id(self):
            return "everywhere"

        def metadata(self):
            return self._metadata

    class _Form:
        def __init__(self, metadata):
            self._integral = _Integral(metadata)

        def integrals(self):
            return (self._integral,)

    original_form = rta_3d.fem.form
    monkeypatch.setattr(rta_3d.fem, "form", lambda value, *_a, **_k: value)

    def fake_absorption(*_a, **_k):
        metadata = {"quadrature_degree": 15, "quadrature_rule": "default"}
        for value in (metadata, metadata, {}, {}):
            rta_3d.fem.form(_Form(value))
        return {"A_volume_total": 1.0}

    monkeypatch.setattr(common_3d_case_flow, "compute_volume_absorption_3d", fake_absorption)
    captured_writer_summaries = []
    real_writer = common_3d_case_flow._write_case_outputs
    writer_calls = []

    def count_real_writer(*args, **kwargs):
        writer_calls.append(Path(args[0]))
        result = real_writer(*args, **kwargs)
        captured_writer_summaries.append(json.loads((Path(args[0]) / "run_summary.json").read_text(encoding="utf-8")))
        return result

    monkeypatch.setattr(common_3d_case_flow, "_write_case_outputs", count_real_writer)

    class _AfterWriter(RuntimeError):
        pass

    stop_after_writer = _AfterWriter("fixture stop after shared writer")

    def fake_solver(cfg, solve_root, *, variable_p_live_observer, **_kwargs):
        view = SimpleNamespace(
            ksp=SimpleNamespace(getPC=lambda: SimpleNamespace(getFactorSolverType=lambda: "mumps")),
            config=cfg,
            goal_context={"modes": modes},
            field=object(),
            mesh_data=mesh_data,
            reduction=SimpleNamespace(
                degree_plan=SimpleNamespace(audit={"trace_degree_values": [6]}),
                system=SimpleNamespace(
                    active_trace_rows=1,
                    entity_map=SimpleNamespace(
                        active_cell_interior_rows=active_interior_rows,
                        active_rows=active_full_rows,
                    ),
                ),
            ),
            A=_ObserverMatrix(),
            b=_ObserverVector(np.ones(613, dtype=np.complex128)),
            x=_ObserverVector(np.ones(613, dtype=np.complex128)),
            full_active_residual={
                "raw_vectors": full_raw,
                "raw_vector_scope": {
                    "reduced_trace_dtn_rows": 613,
                    "reduced_trace_dtn_owned_range": [0, 613],
                    "mpi_size": 1,
                },
                "linear_system_relative_residual": 0.0,
            },
            normal_correction_raw_vectors=normal_vectors,
            primal_solver_telemetry={
                "normal_correction_count": 1,
                "normal_correction_audit": {
                    "status": "passed",
                    "correction_ksp": {"converged_reason": 2},
                },
            },
            port_metrics={"R_total": 0.0, "T_total": 0.0},
        )
        variable_p_live_observer(view)
        solve_root.mkdir(parents=True, exist_ok=True)
        payload = {
            "orders": rows,
            "metrics": {
                "R_total": 0.0,
                "T_total": 0.0,
                "R00_s": 0.0,
                "R00_p": 0.0,
                "R00_total": 0.0,
                "dtn_port_mode_count": 612,
            },
        }
        (solve_root / "dtn_port_diffraction_orders_3d.json").write_text(
            json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8"
        )
        common_3d_case_flow.compute_volume_absorption_3d(cfg, solve_root)
        summary = {
            "case_status": "completed",
            "official_result": False,
            "actual_pc_factor_solver_type": "mumps",
            "A_volume_total": 1.0,
            "timings_seconds": {"fixture": 0.0},
            "cell_static_condensation_audit": {
                "full_operator_true_residual": {"raw_vectors": full_raw},
                "full_explicit_true_residual": {"raw_vectors": full_raw},
            },
        }
        common_3d_case_flow._write_case_outputs(
            solve_root, summary, ["fixture solver log"], h100_anchor.MPI.COMM_WORLD
        )
        if fail_after_writer:
            raise stop_after_writer
        return summary

    monkeypatch.setattr(h100_anchor, "run_stage4b_block_grating_3d_case", fake_solver)

    run_root = tmp_path / "F1/run"
    stage_root = run_root.parent
    args = ["--contract", str(CONTRACT), "--stage", "F1", "--stage-root", str(stage_root)]
    if fail_after_writer:
        with pytest.raises(_AfterWriter, match="after shared writer") as caught:
            r10_h67_diagnostic.main(args)
        assert caught.value is stop_after_writer
        terminal_path = run_root / "v21_f1_terminal.json"
        terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
        assert terminal["status"] == "FAILED_OR_INCOMPLETE"
        assert (run_root / "primary_state.npz").is_file()
        assert (run_root / "primary_raw_vector_audit.json").is_file()
    else:
        assert r10_h67_diagnostic.main(args) == 0
        terminal = json.loads(
            (run_root / "v21_f1_terminal.json").read_text(encoding="utf-8")
        )
        assert terminal["status"] == "SOLVED_PENDING_POSTPROCESS"
        endpoint = json.loads(
            (run_root / "task43_round1_candidate_record.json").read_text(encoding="utf-8")
        )
        assert endpoint["gates"]["pass"] is True
        assert endpoint["gates"]["actual_R10_H67_absorption_forms_observed"] is True
        assert endpoint["primary_raw_vector_audit"]["pass"] is True
        assert endpoint["primary_raw_vector_audit_checkpoint"]["path"].endswith(
            "primary_raw_vector_audit.json"
        )
    assert writer_calls == [run_root / "solve"]
    assert captured_writer_summaries
    assert (run_root / "solve/run_summary.json").is_file()
    assert terminal["phase"] == "R10_H67"
    assert terminal["candidate_id"] == "v21_r10_h67"
    assert phase_checks and phase_checks[0] is (not fail_after_writer)


def _pending_candidate_fixture(
    root: Path, *, mixed_rhs: bool = False, mixed_coefficients: bool = False
):
    from src.test.test_task43_v11_scientific_restart import (
        _raw_gate_arguments,
        _raw_vectors,
    )
    from benchmarks.task43_hp_adaptivity.candidate_checkpoints import write_atomic_npz
    from benchmarks.task43_hp_adaptivity import compare_round1_candidate as comparison

    candidate_root = root / "formal/run"
    (candidate_root / "solve").mkdir(parents=True)
    plan_path = candidate_root / "candidate_plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "task43_candidate": {
                    "candidate_id": "v21_r10_h67",
                    "action": "h_refine",
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )
    plan_sha = _sha256(plan_path)
    acceptance = root / "acceptance.json"
    acceptance.write_text("{}\n", encoding="utf-8")
    acceptance_sha = _sha256(acceptance)

    storage_arrays = {
        "mesh_geometry_coordinates_nm": np.asarray(
            [[x, y, z] for x in (0.0, 1.0) for y in (0.0, 1.0) for z in (0.0, 1.0)],
            dtype=np.float64,
        ),
        "mesh_geometry_dofmap": np.arange(8, dtype=np.int32).reshape(1, 8),
        "mesh_owned_cell_global_ids": np.asarray([67], dtype=np.int64),
        "mesh_cell_vertex_dofmap": np.arange(8, dtype=np.int32).reshape(1, 8),
        "p6_function_space_dofmap": np.arange(8, dtype=np.int32).reshape(1, 8),
        "p6_owned_global_dof_block_ids": np.asarray([0], dtype=np.int64),
        "p6_ghost_global_dof_block_ids": np.asarray([], dtype=np.int64),
        "recovered_p6_local_coefficients": np.asarray([1.0 + 0.0j], dtype=np.complex128),
    }
    stored_coefficients = storage_arrays["recovered_p6_local_coefficients"]
    np.savez_compressed(
        candidate_root / "candidate_recovered_solution_storage.npz",
        **storage_arrays,
    )
    storage_path = candidate_root / "candidate_recovered_solution_storage.npz"
    storage_record = {
        "file": str(storage_path),
        "sha256": _sha256(storage_path),
        "independent_active_fe_dofs": 2,
        "active_trace_rows": 1,
        "active_cell_interior_rows": 1,
        "arrays": {
            name: comparison._checkpoint_array_identity(value)
            for name, value in storage_arrays.items()
        },
    }
    vectors = _raw_vectors()
    if mixed_rhs:
        vectors["returned_trace_dtn_rhs"] = vectors["returned_trace_dtn_rhs"].copy()
        vectors["returned_trace_dtn_rhs"][0] += 1
    packet_coefficients = stored_coefficients.copy()
    if mixed_coefficients:
        packet_coefficients[0] += 1
    packet_arrays = dict(vectors)
    packet_arrays.update(
        {
            f"recovered_{name}": (
                packet_coefficients if name == "recovered_p6_local_coefficients" else value
            )
            for name, value in storage_arrays.items()
        }
    )
    arguments = _raw_gate_arguments()
    candidate_identity = {
        "candidate_id": "v21_r10_h67",
        "action": "h_refine",
        "plan_sha256": plan_sha,
        "acceptance_contract_sha256": acceptance_sha,
    }
    packet = write_atomic_npz(
        candidate_root / "primary_state.npz",
        packet_arrays,
        schema="task43.v21.r10_h67.primary_state.v1",
        classification="fixture_nonofficial",
        identity={
            "phase": "R10_H67",
            "contract_sha256": "a" * 64,
            "candidate_id": "v21_r10_h67",
            "candidate_identity": candidate_identity,
            "candidate_plan_sha256": plan_sha,
            "independent_active_fe_dofs": 2,
            "normal_correction_audit": {
                "correction_ksp": {"converged_reason": 2},
                "status": "passed",
            },
            "normal_correction_count": 1,
            "extra_correction_count": 0,
            "raw_full_active_scope": arguments["full_active_scope"],
            "independent_A6_raw_vector_scope": arguments["independent_a6_scope"],
        },
    )
    mode_path = candidate_root / "solve/dtn_port_diffraction_orders_3d.json"
    mode_path.write_text('{"metrics":{}}\n', encoding="utf-8")
    record = {
        "schema": "task43.round1_candidate_solve.v1",
        "candidate_identity": candidate_identity,
        "gates": {"pass": True},
        "solver": {"official_result": False},
        "resolved_config": {"case_name": "v21_pending_fixture"},
        "numerical_controls": {"mesh": {"fixture_mesh": True}},
        "recovered_solution_storage": storage_record,
        "power": {
            "channel_rows_sha256": _sha256(mode_path),
            "aggregate": {
                key: 0.0
                for key in ("R_total", "T_total", "R00_s", "R00_p", "R00_total")
            },
            "A_volume_total": 1.0,
        },
    }
    endpoint_path = candidate_root / "task43_round1_candidate_record.json"
    endpoint_path.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")
    terminal = {
        "status": "SOLVED_PENDING_POSTPROCESS",
        "candidate_id": "v21_r10_h67",
        "contract": {"sha256": "a" * 64},
        "candidate_plan_sha256": plan_sha,
        "primary_packet": packet,
        "endpoint_record": {"sha256": _sha256(endpoint_path)},
    }
    (candidate_root / "v21_f1_terminal.json").write_text(
        json.dumps(terminal, sort_keys=True) + "\n", encoding="utf-8"
    )
    watchdog_root = candidate_root.parent / "watchdog"
    watchdog_root.mkdir()
    (watchdog_root / "summary.json").write_text(
        json.dumps(
            {
                "classification": "COMPLETED",
                "leader_exit_code": 0,
                "descendants_cleared": True,
                "remaining_child_pids": [],
            }
        )
    )
    (candidate_root.parent / "launcher_terminal.json").write_text(
        json.dumps(
            {
                "supervisor_exit_code": 0,
                "watchdog_exit_code": 0,
                "whole_limit_pass": True,
                "received_signal": None,
            }
        )
    )
    return candidate_root, record, candidate_identity, acceptance, packet


@pytest.mark.parametrize("mixed_rhs", [False, True])
def test_10_v21_pending_reader_recomputes_rebound_raw_packet(
    tmp_path, mixed_rhs
):
    from benchmarks.task43_hp_adaptivity import compare_round1_candidate as comparison

    candidate_root, record, _identity, _acceptance, _packet = _pending_candidate_fixture(
        tmp_path, mixed_rhs=mixed_rhs
    )
    if mixed_rhs:
        with pytest.raises(ValueError, match="do not match the returned system"):
            comparison._validate_v21_pending_candidate(
                candidate_root, record, {}, "a" * 64
            )
    else:
        raw_audit = comparison._validate_v21_pending_candidate(
            candidate_root, record, {}, "a" * 64
        )
        assert raw_audit["pass"] is True


@pytest.mark.parametrize("mixed_coefficients", [False, True])
def test_11_v21_restore_accepts_consistent_packet_and_rejects_mixed_coefficients(
    tmp_path, monkeypatch, mixed_coefficients
):
    from types import SimpleNamespace
    from benchmarks.task43_hp_adaptivity import compare_round1_candidate as comparison

    candidate_root, _record, _identity, acceptance, _packet = _pending_candidate_fixture(
        tmp_path, mixed_coefficients=mixed_coefficients
    )
    monkeypatch.setattr(comparison, "ACCEPTANCE", acceptance)
    fake_mesh_data = SimpleNamespace(mesh=object())
    monkeypatch.setattr(
        comparison,
        "build_stage4_local_h_mesh_data",
        lambda *_args, **_kwargs: fake_mesh_data,
    )
    monkeypatch.setattr(comparison.base, "_axes_from_mesh", lambda _mesh: ())
    monkeypatch.setattr(
        comparison,
        "_assert_mesh_profile",
        lambda *_args, **_kwargs: {"fixture_mesh": True},
    )
    monkeypatch.setattr(
        comparison,
        "_create_nedelec_space",
        lambda *_args: SimpleNamespace(
            dofmap=SimpleNamespace(
                index_map=SimpleNamespace(size_local=1), num_ghosts=0
            )
        ),
    )
    with np.load(candidate_root / "candidate_recovered_solution_storage.npz") as archive:
        stored_arrays = {
            name: np.asarray(archive[name]).copy() for name in archive.files
        }
    monkeypatch.setattr(
        comparison.base,
        "_actual_mesh_identity",
        lambda *_args: {
            "mesh_geometry_coordinates_nm": stored_arrays[
                "mesh_geometry_coordinates_nm"
            ],
            "mesh_geometry_dofmap": stored_arrays["mesh_geometry_dofmap"],
            "mesh_owned_cell_global_ids": stored_arrays[
                "mesh_owned_cell_global_ids"
            ],
            "mesh_cell_vertex_dofmap": stored_arrays["mesh_cell_vertex_dofmap"],
            "p6_function_space_cell_dofmap": stored_arrays[
                "p6_function_space_dofmap"
            ],
            "p6_owned_global_dof_block_ids": stored_arrays[
                "p6_owned_global_dof_block_ids"
            ],
            "p6_ghost_global_dof_block_ids": stored_arrays[
                "p6_ghost_global_dof_block_ids"
            ],
        },
    )

    class _FakeField:
        def __init__(self, *_args, **_kwargs):
            self.x = SimpleNamespace(
                array=np.zeros(1, dtype=np.complex128),
                scatter_forward=lambda: None,
            )

        def scatter_forward(self):
            return None

    monkeypatch.setattr(comparison.fem, "Function", _FakeField)
    if mixed_coefficients:
        with pytest.raises(ValueError, match="differ from primary"):
            comparison._restore_candidate(
                candidate_root,
                tmp_path / "restore",
                v21_contract={},
                v21_contract_sha256="a" * 64,
            )
    else:
        restored = comparison._restore_candidate(
            candidate_root,
            tmp_path / "restore",
            v21_contract={},
            v21_contract_sha256="a" * 64,
        )
        assert restored["label"] == "v21_r10_h67"
        assert restored["v21_restoration_binding"]["same_array_values_dtype_and_shape"] is True
@pytest.mark.parametrize("failure", [None, "q10"])
def test_v21_actual_common_comparison(tmp_path, monkeypatch, failure):
    """Real partition, metrics, root sums and writers; replace only FE restore/sampling."""
    from types import SimpleNamespace
    from benchmarks.task43_hp_adaptivity import compare_round1_candidate as c
    from benchmarks.task43_hp_adaptivity import r10_h67_diagnostic as d
    from benchmarks.task43_hp_adaptivity import h100_anchor as h
    root = tmp_path / "repo"
    prefix = root / "benchmarks/artifacts/task43/v21_r10_h67"
    stage = prefix / "support/comparison_attempt1"
    formal = prefix / "formal/R10_H67_attempt1/run"
    stage.mkdir(parents=True); formal.mkdir(parents=True)
    (root / "source.py").write_text("# fixture source\n")
    (root / "input.json").write_text('{}\n')
    contract = {"artifact_prefix": "benchmarks/artifacts/task43/v21_r10_h67", "slots": {"C": {"root": "support/comparison_attempt1"}, "F1": {"root": "formal/R10_H67_attempt1"}}, "source_paths": ["source.py"], "inputs": {"r10_record": {"path": "input.json", "sha256": d.sha256_file(root / "input.json")}}}
    contract_path = root / "contract.json"; contract_path.write_text(json.dumps(contract))
    contract_sha = d.sha256_file(contract_path)
    monkeypatch.setattr(d, "ROOT", root); monkeypatch.setattr(c, "ROOT", root)
    monkeypatch.setattr(d, "CONTRACT_REL", Path("contract.json"))
    # The strict contract reader has its own actual-file tests; this fixture supplies an isolated contract.
    monkeypatch.setattr(d, "load_contract", lambda _path: (contract, contract_sha))
    products = {}
    for key in ("space_plan", "space_audit", "formal_terminal", "formal_record", "primary_packet", "primary_raw_audit", "formal_storage", "formal_plan", "formal_modal", "formal_absorption", "formal_watchdog", "formal_launcher"):
        path = root / (key + '.json'); path.write_text(json.dumps({"dofs": {"independent_active_fe_dofs": 125000}}))
        products[key] = {"path": str(path), "sha256": d.sha256_file(path)}
    (formal / "candidate_plan.json").write_bytes(Path(products["space_plan"]["path"]).read_bytes())
    (stage / "root_release.json").write_text(json.dumps({"decision": "ALLOW_ONE_FIXED_SLOT", "stage": "C", "contract_sha256": contract_sha, "products": products}))
    # Reuse the actual task worker identity; no second native process or mesh is started.
    original_identity = h._require_v11_watchdog_worker_identity
    monkeypatch.setattr(h, "_require_v11_watchdog_worker_identity", lambda **kw: original_identity(**{**kw, "require_unused_phase_file": False}))
    cfg = h._h100_config(kind="empty_h_active_p3", case_name="v21_compare_fixture", geometry_profile="initial_180")
    axes = tuple(np.asarray(a, dtype=float) for a in ([0,16.5,33.5,50], list(range(0,51,5)), [-10,0,30,60,90,120,130]))
    root_boxes = [(axes[0][i],axes[1][j],axes[2][k],axes[0][i+1],axes[1][j+1],axes[2][k+1]) for i in range(3) for j in range(10) for k in range(6)]
    new_axes = tuple(np.unique(np.r_[a, b]) for a,b in zip(axes, [25,12.5,105]))
    controls = {"volume_quadrature_degree":15,"incident_and_port_quadrature_degree":28,"volume_quadrature_rule":"default","sparse_cutoff_policy":"scale_homogeneous_relative_only_v1","sparse_cutoff_relative_tolerance":1e-13,"ordered_mode_count":612,"port_amplitude_scale_policy":"boundary_magnitude_scaled_r5_v1"}
    rows = [{**c._mode_identity(mode), "kz":c.base._complex_components(mode.k_vector[2]), "direction":"outgoing_up" if mode.side=="top" else "outgoing_down", "medium":"air" if mode.side=="top" else "substrate", "power_carrying":c._mode_carries_outward_power(mode), "outgoing_amplitude":[0,0], "outgoing_amplitude_at_boundary":[0,0], "power_ratio":0.0,"R":0.0,"T":0.0} for mode in c.outgoing_port_modes_3d(cfg)]
    cases = {}
    for label,fe in [("R10",118800),("R10_H67",125000),("Y6_1",380160)]:
        forest = SimpleNamespace(root_boxes=root_boxes, leaves=[SimpleNamespace(key=SimpleNamespace(root=127,level=1))])
        cases[label] = {"label":label,"cfg":cfg,"mesh_data":SimpleNamespace(mesh=label,local_h_context=SimpleNamespace(forest=forest)),"axes":new_axes if label=="R10_H67" else axes,"record":{"numerical_controls":controls,"resolved_identity":{"quadrature_and_cutoff":{"volume_degree":15,"surface_and_incident_degree":28,"volume_rule":"default","cutoff_policy":"scale_homogeneous_relative_only_v1","cutoff_relative_tolerance":1e-13}},"recovered_solution_storage":{"independent_active_fe_dofs":fe}},"mode_payload":{"orders":rows},"power":{k:0.0 for k in ("R_total","T_total","R00_s","R00_p","R00_total","A_volume")},"mesh_identity":{}}
    monkeypatch.setattr(c,"_restore_candidate", lambda path,*a,**kw: cases["R10_H67" if kw.get("v21_contract") else "R10"])
    monkeypatch.setattr(c,"_restore_case_fields", lambda *a,**kw: cases["Y6_1"])
    calls=[]
    def sample(case,points):
        calls.append((case['label'],len(points)))
        if failure=="q10" and len(calls)==6: raise OSError("injected q10 fixture sampling failure")
        value={"Y6_1":1.,"R10":1.+2e-5,"R10_H67":1.+1e-5}[case['label']]
        return {"E":np.full((len(points),3),value,dtype=np.complex128),"curl_E":np.zeros((len(points),3),dtype=np.complex128)}
    monkeypatch.setattr(c,"_sample_field",sample)
    def owners(mesh,axes,points):
        # Synthetic FE boundary only: actual common rule and parent-box coverage are untouched.
        slots=np.zeros(len(points),dtype=np.int64)
        return np.asarray([0]),slots
    monkeypatch.setattr(c.base,"_cell_slot_for_points",owners)
    if failure:
        with pytest.raises(OSError,match='injected q10'):
            c.compare_v21_h67(contract_path,stage/'comparison',formal)
        assert (stage/'comparison/q8_results.json').exists()
        assert json.loads((stage/'comparison/failure.json').read_text())['status']=='FAILED'
        assert not (stage/'comparison/comparison.json').exists()
    else:
        result=c.compare_v21_h67(contract_path,stage/'comparison',formal)
        assert result['status']=='COMPLETE_DIAGNOSTIC_NOT_ACCEPTANCE'
        assert result['Delta_FE']==6200 and not result['transition_written']
        for q in ('q8','q10'):
            table=result['results'][q]['root_responses']
            assert len(table['cells'])==180
            assert table['totals']['before_G_squared'] > table['totals']['after_G_squared'] > 0
        with np.load(stage/'comparison/shared_q10.npz',allow_pickle=False) as archive:
            points=archive['points_nm']
            assert not np.any(points[:,0]==25.)
        assert len(calls)==6
def test_v21_snapshot_requires_the_same_input_and_source_set(tmp_path, monkeypatch):
    d=r10_h67_diagnostic
    monkeypatch.setattr(d,'ROOT',tmp_path)
    monkeypatch.setattr(d,'CONTRACT_REL',Path('contract.json'))
    for name in ('source.py','extra.py','input.json','contract.json'):
        (tmp_path/name).write_text('{}\n')
    contract={'source_paths':['source.py'],'inputs':{'input':{'path':'input.json','sha256':_sha256(tmp_path/'input.json')}}}
    sources,inputs=d.source_snapshot(contract),d.input_snapshot(contract)
    assert d.require_snapshot_equal(contract,source_before=sources,input_before=inputs)==(sources,inputs)
    contract['source_paths'].append('extra.py')
    with pytest.raises(RuntimeError,match='source bytes'):
        d.require_snapshot_equal(contract,source_before=sources,input_before=inputs)
    contract['source_paths'].pop()
    contract['inputs']['another_role']={'path':'input.json','sha256':inputs['input']}
    with pytest.raises(RuntimeError,match='input bytes'):
        d.require_snapshot_equal(contract,source_before=sources,input_before=inputs)
