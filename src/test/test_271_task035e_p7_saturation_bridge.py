from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile

from mpi4py import MPI
import numpy as np
import pytest

from benchmarks.task035e_p7_saturation_bridge import (
    P7SaturationBridgeError,
    build_p7_saturation_structural_evidence,
    candidate_binding_from_authority,
    candidate_binding_from_payload,
    candidate_binding_payload,
    write_p7_saturation_structural_evidence,
)
from src.adaptivity.stage4_local_h import (
    Stage4LocalHContext,
    build_stage4_local_h_mesh_data,
    build_stage4_local_h_reduction_authority,
    stage4_multilevel_local_h_refinement_plan_payload,
)
from src.common.config_3d import target_stage4_config


_STAGE_ONE = (
    (0.0, 0.0, 120.0, 16.5, 12.5, 130.0),
    (33.5, 12.5, 60.0, 50.0, 25.0, 120.0),
)
_STAGE_TWO = (
    (0.0, 0.0, 120.0, 8.25, 6.25, 125.0),
    (41.75, 18.75, 90.0, 50.0, 25.0, 120.0),
)


def _shared_plan_path(payload: dict[str, object]) -> Path:
    comm = MPI.COMM_WORLD
    root = (
        tempfile.mkdtemp(prefix="task035e-p7-bridge-")
        if comm.rank == 0
        else None
    )
    root = comm.bcast(root, root=0)
    path = Path(root) / "multilevel-p6.json"
    if comm.rank == 0:
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    comm.Barrier()
    return path


@pytest.fixture(scope="module")
def bridge_fixture():
    comm = MPI.COMM_WORLD
    cfg = target_stage4_config(degree=6, h_nm=100.0)
    payload = stage4_multilevel_local_h_refinement_plan_payload(
        cfg,
        (_STAGE_ONE, _STAGE_TWO),
        comm_size=comm.size,
        trace_degree=4,
        cell_interior_degree=6,
        provenance={
            "purpose": "Task035e p7 structural bridge fixture",
            "accuracy_credit": False,
            "ordinary_default_changed": False,
        },
        cell_interior_degree_overrides={},
        variable_trace_from_cell_degrees=True,
    )
    path = _shared_plan_path(payload)
    mesh_data = build_stage4_local_h_mesh_data(
        cfg,
        path,
        comm=comm,
    )
    context = mesh_data.local_h_context
    assert isinstance(context, Stage4LocalHContext)
    reduction = build_stage4_local_h_reduction_authority(
        context,
        phase_x=np.exp(0.2j),
        phase_y=np.exp(-0.3j),
    )
    binding = candidate_binding_from_authority(
        context=context,
        reduction=reduction,
        source_sha="a" * 40,
        cycle_index=3,
        output_sha256="b" * 64,
    )
    evidence = build_p7_saturation_structural_evidence(
        context=context,
        reduction=reduction,
        binding=binding,
    )
    return context, reduction, binding, evidence


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="serial diagnostic contract",
)
def test_bridge_enumerates_real_plan_without_numerical_credit(
    bridge_fixture,
) -> None:
    context, reduction, _binding, evidence = bridge_fixture

    assert evidence["evidence_closed"] is True
    assert evidence["binding_audit"]["pass"] is True
    assert evidence["enumeration"]["pass"] is True
    assert evidence["enumeration"]["forest_leaf_count"] == len(
        context.forest.leaves
    )
    assert evidence["enumeration"]["p6_leaf_count"] == len(
        context.forest.leaves
    )
    assert len(evidence["enumeration"]["p6_target_ids"]) == len(
        context.forest.leaves
    )
    assert evidence["production_numbering"][
        "inactive_p7_numbering_pass"
    ] is True
    assert evidence["production_numbering"]["p7_rows_added"] == 0
    assert evidence["production_numbering"]["active_rows"] == (
        reduction.trace_constraints.entity_map.active_rows
    )
    assert evidence["p7_component_binding"]["component_pass"] is True
    assert evidence["numerical_saturation_status"] == "unknown"
    assert evidence["measured_pass"] is False
    assert evidence["accuracy_credit"] is False
    assert evidence["selectable_as_production"] is False
    assert evidence["formal_coverage_semantics"][
        "p7_tensor_evaluation_status"
    ] == "not_run"
    assert evidence["structural_coverage_pass"] is False
    assert evidence["mathematical_structural_coverage_pass"] is True
    assert "formal_mpi8_partition_not_executed" in evidence[
        "blocker_codes"
    ]
    assert evidence["p7_component_binding"][
        "hanging_component_available"
    ] is True
    assert evidence["p7_component_binding"][
        "mixed_p4_p5_p6_injection_component_available"
    ] is True
    distribution = evidence["mathematical_audit_distribution"]
    assert distribution["execution_rank"] == 0
    assert distribution["canonical_broadcast"] is True
    assert distribution["request_all_rank_digest_pass"] is True
    assert (
        distribution["mathematical_audit_all_rank_validation_pass"]
        is True
    )
    assert "p7_hanging_trace_transform_failed" not in evidence[
        "blocker_codes"
    ]


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="serial diagnostic contract",
)
def test_binding_round_trip_tamper_and_self_hash(
    bridge_fixture,
    tmp_path: Path,
) -> None:
    _context, _reduction, binding, evidence = bridge_fixture
    replay = candidate_binding_from_payload(
        candidate_binding_payload(binding)
    )
    assert replay == binding

    output = tmp_path / "p7-structural-evidence.json"
    file_sha = write_p7_saturation_structural_evidence(
        output,
        evidence,
    )
    outer = json.loads(output.read_text(encoding="utf-8"))
    assert len(file_sha) == 64
    assert outer["sha256"] == evidence["evidence_sha256"]
    assert output.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        write_p7_saturation_structural_evidence(output, evidence)

    with pytest.raises(
        P7SaturationBridgeError,
        match="structural identity differs",
    ):
        build_p7_saturation_structural_evidence(
            context=_context,
            reduction=_reduction,
            binding=replace(
                binding,
                forest_leaf_catalog_sha256="c" * 64,
            ),
        )


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="serial diagnostic contract",
)
def test_bridge_evidence_is_deterministic(bridge_fixture) -> None:
    context, reduction, binding, first = bridge_fixture
    second = build_p7_saturation_structural_evidence(
        context=context,
        reduction=reduction,
        binding=binding,
    )

    assert second["evidence_sha256"] == first["evidence_sha256"]
    assert second["mpi"]["all_rank_digest_sha256"] == first["mpi"][
        "all_rank_digest_sha256"
    ]
    assert second["enumeration"]["p6_target_ids_sha256"] == first[
        "enumeration"
    ]["p6_target_ids_sha256"]


@pytest.mark.skipif(
    os.environ.get("MYFENICS_RUN_TASK035E_P7_BRIDGE_MPI8") != "1"
    or MPI.COMM_WORLD.size != 8,
    reason="set the opt-in flag and launch this fixture with MPI8",
)
def test_bridge_mpi8_all_rank_digest_is_closed(bridge_fixture) -> None:
    _context, _reduction, _binding, evidence = bridge_fixture

    assert evidence["mpi"]["observed_size"] == 8
    assert evidence["mpi"]["all_rank_digest_pass"] is True
    assert len(set(evidence["mpi"]["digest_by_rank"])) == 1
    assert evidence["mpi"]["formal_partition_identity_status"] == "pass"
    assert all(evidence["mpi"]["ownership_checks"].values())
    assert "formal_mpi8_partition_not_executed" not in evidence[
        "blocker_codes"
    ]
    assert evidence["mathematical_structural_coverage_pass"] is True
    assert evidence["structural_coverage_pass"] is True
    assert evidence["blocker_codes"] == []
    distribution = evidence["mathematical_audit_distribution"]
    assert distribution["execution_rank"] == 0
    assert distribution["canonical_broadcast"] is True
    assert len(set(distribution["request_digest_by_rank"])) == 1
    assert len(
        set(distribution["mathematical_audit_digest_by_rank"])
    ) == 1
    assert distribution["request_all_rank_digest_pass"] is True
    assert all(
        distribution["mathematical_audit_validation_by_rank"]
    )
    assert (
        distribution["mathematical_audit_all_rank_validation_pass"]
        is True
    )
    assert distribution["each_rank_rederived_request_catalog"] is True
    assert distribution["each_rank_verified_broadcast_digest"] is True
    assert evidence["numerical_saturation_status"] == "unknown"
    assert evidence["measured_pass"] is False
