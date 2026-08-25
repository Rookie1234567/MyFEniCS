"""Focused PETSc tests for the V4 exact-authority compatibility audit."""

from __future__ import annotations

import json

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

import benchmarks.task040_level_a as level_a
import benchmarks.task040_level_a_watchdog as watchdog
from src.solvers.hybrid_exact_authority_compat import (
    V4_CANONICAL_SOURCE_BRIDGE_NOT_QUALIFIED,
    V4_CANONICAL_SOURCE_BINDING_REASON,
    V4_CANONICAL_SOURCE_BINDING_UNAVAILABLE,
    V4_EXACT_AUTHORITY_FAILURE,
    V4_EXACT_AUTHORITY_LABELS,
    audit_exact_authority_petsc,
    canonical_binding_failure_audit,
    inspect_canonical_source_authority,
)


def _canonical_descriptor(index: int = 0) -> dict[str, str]:
    return {
        "map_path": f"canonical-source-map-{index}.jsonl",
        "map_sha256": f"{index + 1:064x}",
        "source_sha": "a" * 40,
        "run_identity_sha256": "b" * 64,
        "partition_sha256": "c" * 64,
        "key_set_sha256": "d" * 64,
    }


def _canonical_spool(*, complete: bool) -> dict[str, dict[str, dict[str, object]]]:
    spool = {}
    for label in V4_EXACT_AUTHORITY_LABELS:
        spool[label] = {}
        for role in ("rhs", "exact_output"):
            shard = {"ownership_range": [0, 3]}
            if complete:
                shard["canonical_source_authority"] = _canonical_descriptor()
            spool[label][role] = {"shards": [shard]}
    return spool


def _preflight_metadata_spool(expected_ids: dict[str, str]):
    spool = _canonical_spool(complete=False)
    for label in V4_EXACT_AUTHORITY_LABELS:
        for role in ("rhs", "exact_output"):
            shards = []
            for rank in range(8):
                shard = {"ownership_range": [3 * rank, 3 * (rank + 1)]}
                shard["source_identity"] = {
                    "packet_identity": {
                        "source_sha": ("7e5d9b57a10b1093f0cb062eaf7bc12797c47e1f"),
                    },
                    "vector_identity": {
                        "global_sha256": expected_ids[label],
                    },
                }
                shards.append(shard)
            spool[label][role]["shards"] = shards
            if role == "rhs":
                spool[label][role]["probe_metadata"] = {"label": label}
    return spool


def test_v4_source_authority_inventory_stops_without_canonical_map() -> None:
    report = inspect_canonical_source_authority(_canonical_spool(complete=False))
    assert report["pass"] is False
    assert report["failure_code"] == V4_CANONICAL_SOURCE_BINDING_UNAVAILABLE
    assert report["reason"] == V4_CANONICAL_SOURCE_BINDING_REASON
    assert len(report["missing_entries"]) == 2 * len(V4_EXACT_AUTHORITY_LABELS)
    assert report["array_hash_validation_only"] is None
    assert report["numeric_vectors_constructed"] is False
    assert report["values_retained"] is False
    assert report["canonical_map_opened"] is False
    assert report["entries"][V4_EXACT_AUTHORITY_LABELS[0]]["rhs"][
        "ownership_ranges"
    ] == [[0, 3]]


def test_v4_source_authority_descriptor_alone_is_not_bridge_qualified() -> None:
    report = inspect_canonical_source_authority(_canonical_spool(complete=True))
    assert report["descriptor_complete"] is True
    assert report["descriptor_available"] is True
    assert report["bridge_qualified"] is False
    assert report["pass"] is False
    assert report["failure_code"] == V4_CANONICAL_SOURCE_BRIDGE_NOT_QUALIFIED
    assert report["missing_entries"] == []
    assert report["malformed_entries"] == []
    assert report["inconsistent_fields"] == []
    json.loads(json.dumps(report, sort_keys=True))


def test_v4_identity_stop_keeps_numerical_fields_not_run() -> None:
    source_binding = inspect_canonical_source_authority(
        _canonical_spool(complete=False)
    )
    audit = canonical_binding_failure_audit(
        identity={"source_sha": "a" * 40},
        source_binding=source_binding,
    )
    assert audit["classification"] == V4_EXACT_AUTHORITY_FAILURE
    assert audit["failure_code"] == V4_CANONICAL_SOURCE_BINDING_UNAVAILABLE
    assert audit["residual_status"] == "not_run_by_identity_gate"
    assert audit["finite_pass"] is None
    assert audit["bare_f_residual_pass"] is None
    assert audit["repeat_pass"] is None
    assert audit["numerical_gate_pass"] is None
    json.loads(json.dumps(audit, sort_keys=True))


def test_v4_source_authority_collective_state_is_consistent() -> None:
    report = inspect_canonical_source_authority(_canonical_spool(complete=False))
    state = {
        "pass": report["pass"],
        "failure_code": report["failure_code"],
        "missing_count": len(report["missing_entries"]),
    }
    assert all(candidate == state for candidate in MPI.COMM_WORLD.allgather(state))


def test_v4_source_preflight_fails_closed_after_array_hash_only_validation(
    monkeypatch, tmp_path
):
    _manifest_path, manifest = level_a._v1_2_load_manifest()
    expected_ids = dict(manifest["physical_probes"]["exact_output_identity_sha256"])
    spool = _preflight_metadata_spool(expected_ids)
    resolved_path = tmp_path / "worker" / "resolved_config.json"
    resolved_path.parent.mkdir()
    resolved_path.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(
        level_a,
        "_v9_frozen_holdout_identity",
        lambda *_args, **_kwargs: (
            {"packet": "identity"},
            manifest["identity"]["selected_manifest_sha256"],
            {},
        ),
    )
    monkeypatch.setattr(
        level_a,
        "_v1_2_validate_spool_identity",
        lambda **_kwargs: manifest["identity"]["exact_spool_catalog_sha256"],
    )
    monkeypatch.setattr(
        level_a,
        "_load_v5_fixed_budget_spool_shards",
        lambda *_args, **_kwargs: spool,
    )
    result = level_a._v4_source_authority_preflight(
        exact_spool_root=tmp_path / "worker" / "spool",
        source_sha="1" * 40,
        input_sha256=manifest["identity"]["input_sha256"],
        physical_model_sha256=manifest["identity"]["physical_model_sha256"],
        comm=MPI.COMM_SELF,
    )
    record = result["result"]
    identity = record["identity_observed"]
    assert record["identity_failure_code"] == V4_CANONICAL_SOURCE_BINDING_UNAVAILABLE
    assert record["residual_status"] == "not_run_by_identity_gate"
    assert identity["current_source_sha"] == "1" * 40
    assert identity["spool_producer_source_sha"] == (
        "7e5d9b57a10b1093f0cb062eaf7bc12797c47e1f"
    )
    assert (
        identity["task040_manifest_freeze_source_sha"]
        == manifest["freeze"]["source_sha_at_freeze"]
    )
    assert identity["source_canonical_authority"]["array_hash_validation_only"] is True
    assert (
        identity["source_canonical_authority"]["numeric_vectors_constructed"] is False
    )
    assert identity["source_canonical_authority"]["values_retained"] is False
    assert identity["identity_checks"]["spool_producer_source"]["pass"] is True
    assert identity["identity_checks"]["exact_output_metadata"]["pass"] is True
    assert identity["identity_checks"]["input_sha256"]["pass"] is True
    assert identity["identity_checks"]["physical_model_sha256"]["pass"] is True
    assert identity["identity_checks"]["frozen_branch"]["pass"] is True
    assert identity["identity_checks"]["freeze_source"]["pass"] is True
    assert identity["identity_checks"]["packet_manifest"]["pass"] is True
    assert identity["identity_checks"]["spool_catalog"]["pass"] is True
    assert identity["identity_checks"]["canonical_source_binding"]["pass"] is False
    assert "resolved_config" in identity["identity_failures"]
    assert "canonical_source_binding" in identity["identity_failures"]
    assert identity["identity_checks_pass"] is False
    json.loads(json.dumps(result, sort_keys=True))


def test_v4_missing_source_sha_on_one_shard_cannot_pass() -> None:
    expected = "7e5d9b57a10b1093f0cb062eaf7bc12797c47e1f"
    spool = _preflight_metadata_spool(
        {label: "x" * 64 for label in V4_EXACT_AUTHORITY_LABELS}
    )
    del spool[V4_EXACT_AUTHORITY_LABELS[0]]["rhs"]["shards"][0]["source_identity"][
        "packet_identity"
    ]["source_sha"]
    report = level_a._v4_spool_producer_source_identity(
        spool,
        V4_EXACT_AUTHORITY_LABELS,
        expected_source_sha=expected,
        expected_mpi_size=8,
    )
    entry = report["per_label_role"][f"{V4_EXACT_AUTHORITY_LABELS[0]}:rhs"]
    assert report["pass"] is False
    assert entry["shard_count"] == 8
    assert entry["valid_source_sha_count"] == 7
    assert entry["expected_match_count"] == 7
    assert entry["check"] is False
    json.loads(json.dumps(report, sort_keys=True))


def test_v4_exact_output_metadata_requires_expected_shard_count() -> None:
    _manifest_path, manifest = level_a._v1_2_load_manifest()
    expected_ids = dict(manifest["physical_probes"]["exact_output_identity_sha256"])
    spool = _preflight_metadata_spool(expected_ids)
    label = V4_EXACT_AUTHORITY_LABELS[0]
    del spool[label]["exact_output"]["shards"][-1]
    report = level_a._v4_spool_metadata_identity(
        spool,
        V4_EXACT_AUTHORITY_LABELS,
        expected_ids,
        expected_mpi_size=8,
    )
    assert report["shard_counts"][label] == 7
    assert report["checks"][label] is False
    assert report["pass"] is False
    json.loads(json.dumps(report, sort_keys=True))


def _matrix(values: np.ndarray) -> PETSc.Mat:
    values = np.asarray(values, dtype=np.complex128)
    size = int(values.shape[0])
    matrix = PETSc.Mat().createAIJ(
        size=((PETSc.DECIDE, size), (PETSc.DECIDE, size)),
        nnz=size,
        comm=MPI.COMM_WORLD,
    )
    first, last = map(int, matrix.getOwnershipRange())
    for row in range(first, last):
        for column in range(size):
            matrix.setValue(row, column, PETSc.ScalarType(values[row, column]))
    matrix.assemble()
    return matrix


def _vector(matrix: PETSc.Mat, values: np.ndarray) -> PETSc.Vec:
    vector = matrix.createVecRight()
    first, last = map(int, vector.getOwnershipRange())
    vector.array[:] = np.asarray(values[first:last], dtype=PETSc.ScalarType)
    vector.assemble()
    return vector


def _authority_data(matrix: PETSc.Mat, exact_values: np.ndarray):
    exact = _vector(matrix, exact_values)
    rhs = matrix.createVecLeft()
    matrix.mult(exact, rhs)
    rhs_vectors = {label: rhs.duplicate() for label in V4_EXACT_AUTHORITY_LABELS}
    exact_vectors = {label: exact.duplicate() for label in V4_EXACT_AUTHORITY_LABELS}
    for vector in rhs_vectors.values():
        rhs.copy(vector)
    for vector in exact_vectors.values():
        exact.copy(vector)
    metadata = {
        label: {"label": label, "kind": "tiny", "seed": index}
        for index, label in enumerate(V4_EXACT_AUTHORITY_LABELS)
    }
    identities = {
        label: f"{index:064x}" for index, label in enumerate(V4_EXACT_AUTHORITY_LABELS)
    }
    return exact, rhs, rhs_vectors, exact_vectors, metadata, identities


def _destroy_vectors(*groups) -> None:
    seen = set()
    for group in groups:
        for vector in group.values() if isinstance(group, dict) else group:
            if id(vector) not in seen:
                vector.destroy()
                seen.add(id(vector))


def test_exact_authority_bare_f_pass_and_identity_is_explicit_aij() -> None:
    values = np.asarray(
        [[2.0 + 0.2j, 0.3 - 0.1j], [0.4 + 0.5j, 1.7 - 0.3j]],
        dtype=np.complex128,
    )
    matrix = _matrix(values)
    exact, rhs, rhs_vectors, exact_vectors, metadata, identities = _authority_data(
        matrix, np.asarray([0.7 + 0.2j, -0.4 + 0.6j])
    )
    try:
        audit = audit_exact_authority_petsc(
            matrix,
            matrix,
            rhs_vectors,
            exact_vectors,
            source_metadata=metadata,
            exact_output_identity_sha256=identities,
            identity={"source_sha": "a" * 40},
            bare_matrix_hash=lambda _matrix: "f" * 64,
        )
        assert audit["gate_pass"] is True
        assert audit["classification"] != V4_EXACT_AUTHORITY_FAILURE
        assert all(
            row["bare_f"]["residual_relative"] <= 1.0e-12 for row in audit["reports"]
        )
        assert audit["operator_identity"]["bare_f"]["matrix_free"] is False
        assert audit["operator_identity"]["a_side"]["matrix_free"] is False
        assert audit["operator_identity"]["a_side"]["action_identity"] == (
            "system.A = F - C H^-1 D"
        )
        assert audit["operator_identity"]["bare_f"]["global_size"] == [2, 2]
        local_size = audit["operator_identity"]["bare_f"]["local_size"]
        ownership = audit["operator_identity"]["bare_f"]["ownership_range"]
        assert local_size[0] == ownership[1] - ownership[0]
        assert all(size >= 0 for size in local_size)
        assert audit["operator_identity"]["bare_f"]["block_size"] == 1
    finally:
        _destroy_vectors(rhs_vectors, exact_vectors, [exact, rhs])
        matrix.destroy()


def test_a_side_only_exact_is_not_bare_f_compatible() -> None:
    side_values = np.asarray(
        [[1.8 + 0.1j, 0.2], [0.1 - 0.3j, 1.4 + 0.2j]], dtype=np.complex128
    )
    bare_values = side_values + np.diag([0.4, -0.25]).astype(np.complex128)
    side = _matrix(side_values)
    bare = _matrix(bare_values)
    exact, rhs, rhs_vectors, exact_vectors, metadata, identities = _authority_data(
        side, np.asarray([0.2 + 0.5j, 1.1 - 0.4j])
    )
    try:
        audit = audit_exact_authority_petsc(
            bare,
            side,
            rhs_vectors,
            exact_vectors,
            source_metadata=metadata,
            exact_output_identity_sha256=identities,
            identity={"source_sha": "b" * 40},
            bare_matrix_hash=lambda matrix: "0" * 64 if matrix is bare else "1" * 64,
        )
        assert audit["classification"] == V4_EXACT_AUTHORITY_FAILURE
        assert audit["gate_pass"] is False
        assert (
            max(row["bare_f"]["residual_relative"] for row in audit["reports"]) > 1.0e-2
        )
        assert (
            max(
                row["a_side_explanatory"]["residual_relative"]
                for row in audit["reports"]
            )
            <= 1.0e-12
        )
    finally:
        _destroy_vectors(rhs_vectors, exact_vectors, [exact, rhs])
        bare.destroy()
        side.destroy()


def test_hash_change_or_nonrepeatable_operator_fails_gate() -> None:
    matrix = _matrix(np.asarray([[1.5 + 0.1j, 0.2], [0.0, 1.2 - 0.2j]]))
    exact, rhs, rhs_vectors, exact_vectors, metadata, identities = _authority_data(
        matrix, np.asarray([1.0 + 0.1j, 0.5 - 0.2j])
    )
    calls = {"count": 0}

    def changing_hash(_matrix: PETSc.Mat) -> str:
        calls["count"] += 1
        return f"{calls['count']:064x}"

    try:
        audit = audit_exact_authority_petsc(
            matrix,
            matrix,
            rhs_vectors,
            exact_vectors,
            source_metadata=metadata,
            exact_output_identity_sha256=identities,
            identity={"source_sha": "c" * 40},
            bare_matrix_hash=changing_hash,
        )
        assert audit["bare_f_hash_unchanged_pass"] is False
        assert audit["gate_pass"] is False
        assert audit["classification"] == V4_EXACT_AUTHORITY_FAILURE
    finally:
        _destroy_vectors(rhs_vectors, exact_vectors, [exact, rhs])
        matrix.destroy()


def test_v4_identity_preflight_skips_system_builder_and_is_json_safe(
    monkeypatch, tmp_path
):
    stop = {
        "result": {
            "schema": "task040.v4.exact_authority_compatibility.v1",
            "identity_failure_code": V4_CANONICAL_SOURCE_BINDING_UNAVAILABLE,
            "residual_status": "not_run_by_identity_gate",
            "construction": {"system_created": False},
        }
    }
    monkeypatch.setattr(
        level_a, "_v4_source_authority_preflight", lambda **_kwargs: stop
    )

    def fail_builder(**_kwargs):
        raise AssertionError("V4 identity stop must precede system construction")

    result = level_a.run_task040_level_a(
        object(),
        object(),
        exact_spool_root=tmp_path / "spool",
        source_sha="a" * 40,
        input_sha256="b" * 64,
        physical_model_sha256="c" * 64,
        side_system_builder=fail_builder,
        v4_exact_authority_compatibility=True,
    )
    assert result["identity_failure_code"] == V4_CANONICAL_SOURCE_BINDING_UNAVAILABLE
    assert result["residual_status"] == "not_run_by_identity_gate"
    assert result["construction"]["system_created"] is False
    json.loads(json.dumps(result, sort_keys=True))


def test_v4_plan_and_watchdog_contract(tmp_path):
    input_path = tmp_path / "input.dat"
    spool_path = tmp_path / "spool"
    run_path = tmp_path / "run"
    plan = level_a.build_task040_level_a_plan(
        input_path=input_path,
        exact_spool_root=spool_path,
        run_directory=run_path,
        source_sha="a" * 40,
        v4_exact_authority_compatibility=True,
    )
    assert plan["schema"] == level_a.TASK040_V4_EXACT_AUTHORITY_COMPATIBILITY_SCHEMA
    assert plan["method"] == level_a.TASK040_V4_EXACT_AUTHORITY_COMPATIBILITY_METHOD
    assert (
        plan["profile"] == level_a.TASK040_V4_EXACT_AUTHORITY_COMPATIBILITY_PROFILE_ID
    )
    assert plan["v4_exact_authority_compatibility"] is True
    assert plan["research_only"] is True
    assert plan["bare_f_compatibility"] == "not_run_by_identity_gate"
    assert plan["read_only_exact_outputs"] is True
    assert plan["expected_exact_output_count"] == 5
    assert plan["exact_output_vectors_loaded"] == 0
    assert plan["qep_calls"] == 0
    assert plan["pde_solve"] == "not_run"
    assert "outer_ksp" in plan["forbidden"]
    assert len(plan["forbidden"]) == len(set(plan["forbidden"]))

    watchdog_plan = watchdog.build_task040_level_a_watchdog_plan(
        input_path=input_path,
        exact_spool_root=spool_path,
        run_directory=tmp_path / "watchdog-run",
        source_sha="b" * 40,
        v4_exact_authority_compatibility=True,
    )
    argv = watchdog_plan["worker_argv"]
    assert argv.count(level_a.TASK040_V4_EXACT_AUTHORITY_COMPATIBILITY_FLAG) == 1
    assert level_a.TASK040_V2_INTERFACE_PACKET_CONSUMER_FLAG not in argv
    assert level_a.TASK040_V2_INTERFACE_PACKET_PRODUCER_FLAG not in argv
    assert watchdog_plan["absolute_terminate_memory_bytes"] == 45 * 2**30
    assert watchdog_plan["watchdog"]["swap_limit_bytes"] == 0
