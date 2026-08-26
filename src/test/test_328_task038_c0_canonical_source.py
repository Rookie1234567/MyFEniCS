"""Pure C0 physical-key source and independent adjoint checks."""

from __future__ import annotations

import json

import numpy as np
from benchmarks.run_task038_full3d_c0_canonical_source import (
    MARKER_SCHEMA as C0_MARKER_SCHEMA,
    SCHEMA as C0_RECORD_SCHEMA,
    _c0_marker,
    _packet_artifact,
)
from benchmarks.task038_full3d_c0_canonical_source_checker import (
    ALPHA,
    BETA,
    CHECK_SCHEMA as C0_CHECK_SCHEMA,
    MARKER_SCHEMA as C0_CHECK_MARKER_SCHEMA,
    SCHEMA as C0_CHECK_RECORD_SCHEMA,
    PACKET_ROLES,
    SOURCE2_SCALE,
    _check_packet_relations,
    _check_source_packets,
    _load_packet_artifact,
    _scalar_relative,
)

from src.solvers.hcurl_canonical_vector import (
    canonical_key,
    canonical_source_coefficient,
    canonical_source_coefficient_from_key,
)


class _MarkerComm:
    rank = 0

    def bcast(self, value, root):
        return value

    def barrier(self):
        return None


class _PacketComm(_MarkerComm):
    size = 1

    def gather(self, value, root):
        return [value]


def test_c0_marker_uses_explicit_serializer_binding(tmp_path) -> None:
    marker_dir = tmp_path / "markers"
    marker_dir.mkdir()
    marker_path = tmp_path / "markers" / "startup.json"
    _c0_marker(
        tmp_path,
        "startup",
        "source-sha",
        _MarkerComm(),
        lambda value: value,
        raw_dir="worker-raw",
        answer=7,
    )
    payload = json.loads(marker_path.read_text())
    assert C0_RECORD_SCHEMA == "task038.full3d.canonical-source.c0-record.v2"
    assert C0_MARKER_SCHEMA == "task038.full3d.canonical-source.c0-marker.v2"
    assert C0_CHECK_RECORD_SCHEMA == C0_RECORD_SCHEMA
    assert C0_CHECK_MARKER_SCHEMA == C0_MARKER_SCHEMA
    assert C0_CHECK_SCHEMA == "task038.full3d.canonical-source.c0-check.v3"
    assert payload["schema"] == C0_MARKER_SCHEMA
    assert payload["facts"] == {"answer": 7, "raw_dir": "worker-raw"}


def test_c0_packet_artifact_uses_explicit_serializer_binding(tmp_path) -> None:
    key = canonical_key(
        role="full_fe",
        entity_dimension=1,
        physical_entity=((0, 0, 0), (0, 0, 4)),
        entity_local_basis_index=0,
        orientation_state=("canonical_edge",),
    )
    descriptor = _packet_artifact(
        tmp_path,
        "source_primal",
        ((key, 1.0 + 2.0j),),
        {"global_packet_count": 1},
        "full_fe",
        _PacketComm(),
        lambda value: value,
    )
    manifest = tmp_path / descriptor["manifest_relative_path"]
    assert manifest.is_file()
    assert len(descriptor["manifest_sha256"]) == 64

    from benchmarks.canonical_vector_artifacts import (
        write_canonical_manifest,
        write_canonical_packet_shard,
    )

    manifest_data = json.loads(manifest.read_text())
    shard_path = manifest.parent / manifest_data["per_rank_shards"][0]["filename"]
    wrong_key = ("active_trace",) + key[1:]
    shard_metadata = write_canonical_packet_shard(
        shard_path, ((wrong_key, 1.0 + 2.0j),), audit_packets=True
    )
    manifest_data["per_rank_shards"] = [shard_metadata]
    manifest_data["global_summed_packet_count"] = 1
    manifest_data["summed_local_duplicate_count"] = 0
    descriptor["manifest_sha256"] = write_canonical_manifest(manifest, manifest_data)
    errors: list[str] = []
    assert _load_packet_artifact(tmp_path, "source_primal", descriptor, 1, errors) == {}
    assert any("key identity mismatch" in item for item in errors)


def test_c0_source_is_partition_and_order_independent() -> None:
    kwargs = {
        "role": "full_fe",
        "physical_entity": ((4, 2, 0), (0, 2, 0)),
        "entity_dimension": 1,
        "entity_local_basis_index": 2,
        "orientation_state": ("canonical_edge", "reverse", (1, 0)),
        "floquet_master": ((0, 2, 0), (0, 0, 0)),
        "floquet_phase_state": (0.25, -0.9682458365518543),
        "fixed_seed": "task038-c0-fixed-seed-v1",
    }
    first = canonical_source_coefficient(**kwargs)
    reordered = canonical_source_coefficient(
        **{**kwargs, "physical_entity": tuple(reversed(kwargs["physical_entity"]))}
    )
    assert first[0].dtype == np.dtype(np.complex128)
    assert first[0] == reordered[0]
    assert first[1] == reordered[1]
    assert first[2] == reordered[2]
    assert np.isfinite(first[0].real) and np.isfinite(first[0].imag)
    assert abs(first[0]) > 0.0

    # These values stand for two different partition/order arrangements; no
    # PETSc row, rank, ownership, or iteration order enters the call.
    assert canonical_source_coefficient(**kwargs)[0].tobytes() == first[0].tobytes()
    assert canonical_source_coefficient(
        **{**kwargs, "fixed_seed": "task038-c0-other-seed"}
    )[1] != first[1]


def test_c0_dependent_slave_source_key_hash_sensitivity() -> None:
    master = ((0, 0, 0), (0, 0, 4))
    slave = ((10, 0, 0), (10, 0, 4))
    key = canonical_key(
        role="full_fe",
        entity_dimension=1,
        physical_entity=slave,
        entity_local_basis_index=0,
        orientation_state=("floquet", "x", (1, 0)),
        floquet_master=master,
        floquet_coefficient=0.3 + 0.9539392014169457j,
    )
    value, digest, payload = canonical_source_coefficient_from_key(
        key, fixed_seed="task038-c0-fixed-seed-v1"
    )
    for field, replacement in (
        ("physical_entity", ((99, 0, 0), (99, 0, 4))),
        ("entity_local_basis_index", 1),
        ("orientation_state", ("floquet", "y", (1, 0))),
        ("floquet_master", ((1, 0, 0), (1, 0, 4))),
        ("floquet_coefficient", 0.4 + 0.916515138991168j),
    ):
        changed = {
            "physical_entity": slave,
            "entity_local_basis_index": 0,
            "orientation_state": key[4],
            "floquet_master": master,
            "floquet_coefficient": complex(*key[6]),
        }
        changed[field] = replacement
        changed_key = canonical_key(
            role="full_fe",
            entity_dimension=1,
            **changed,
        )
        changed_value, changed_digest, _ = canonical_source_coefficient_from_key(
            changed_key, fixed_seed="task038-c0-fixed-seed-v1"
        )
        assert changed_digest != digest
        assert changed_value.tobytes() != value.tobytes()
    assert np.isfinite(value.real) and np.isfinite(value.imag)
    assert payload["floquet_master_phase_state"]["master"] is not None


def test_c0_independent_local_ph_adjoint_uses_conjugate_transpose() -> None:
    matrix = np.asarray(
        [[1.0 + 2.0j, 3.0 - 1.0j], [0.5 + 4.0j, -2.0 + 0.25j]],
        dtype=np.complex128,
    )
    coarse = np.asarray([1.25 - 0.5j, -0.75 + 2.0j], dtype=np.complex128)
    fine = np.asarray([2.0 + 0.25j, -1.0 + 0.75j], dtype=np.complex128)
    coarse_before = coarse.copy()
    fine_before = fine.copy()
    projected = matrix @ coarse
    explicit_adjoint = matrix.conj().T @ fine
    lhs = np.vdot(projected, fine)
    rhs = np.vdot(coarse, explicit_adjoint)
    assert np.isclose(lhs, rhs, rtol=1.0e-14, atol=1.0e-14)
    assert np.array_equal(coarse, coarse_before)
    assert np.array_equal(fine, fine_before)
    assert np.array_equal(projected, matrix @ coarse)
    assert np.array_equal(explicit_adjoint, matrix.conj().T @ fine)


def test_c0_checker_recomputes_global_source_and_work_relations() -> None:
    seed = "task038-c0-physical-canonical-source-v1"
    master_entity = ((0, 0, 0), (0, 0, 4))
    slave_entity = ((10, 0, 0), (10, 0, 4))
    master_key = canonical_key(
        role="full_fe",
        entity_dimension=1,
        physical_entity=master_entity,
        entity_local_basis_index=0,
        orientation_state=("canonical_edge", "lexicographic_xyz", "v1"),
        floquet_master=None,
        floquet_coefficient=1.0,
    )
    slave_key = canonical_key(
        role="full_fe",
        entity_dimension=1,
        physical_entity=slave_entity,
        entity_local_basis_index=0,
        orientation_state=("floquet", "x", "v1"),
        floquet_master=master_entity,
        floquet_coefficient=0.3 + 0.9539392014169457j,
    )
    master_value, _digest, _payload = canonical_source_coefficient_from_key(
        master_key, fixed_seed=seed
    )
    source_facts = {
        "schema": "task038.v13.c0.physical-canonical-source.v1",
        "role": "full_fe",
        "fixed_seed": seed,
        "global_packet_count": 2,
        "global_independent_packet_count": 1,
        "global_dependent_packet_count": 1,
        "dependent_placeholder_non_authoritative": True,
        "dependent_value_authority": "finalized_mpc_master_phase_relation",
        "source_finite": True,
        "source_nonzero": True,
        "source_generation": "physical_canonical_key_sha256_v1",
        "phase_application": "finalized_floquet_mpc_once",
    }
    source_errors: list[str] = []
    source_gates: list[str] = []
    source_metrics = _check_source_packets(
        "source_primal",
        {master_key: complex(master_value), slave_key: complex(master_value) * (1.0 + 1.0e-15)},
        source_facts,
        seed,
        source_errors,
        source_gates,
    )
    assert source_errors == []
    assert source_gates == []
    assert source_metrics["global_packet_count"] == 2
    assert source_metrics["dependent_relation_relative"] <= 1.0e-13

    dual_key = canonical_key(
        role="full_fe_dual",
        entity_dimension=2,
        physical_entity=((0, 0, 0), (0, 0, 4), (0, 4, 0), (0, 4, 4)),
        entity_local_basis_index=0,
        orientation_state=("canonical_face", "v1"),
    )
    dual_value_expected, _digest, _payload = canonical_source_coefficient_from_key(
        dual_key, fixed_seed=seed
    )
    dual_facts = dict(source_facts)
    dual_facts.update(
        {
            "role": "full_fe_dual",
            "global_packet_count": 1,
            "global_independent_packet_count": 1,
            "global_dependent_packet_count": 0,
            "dependent_placeholder_non_authoritative": False,
            "dependent_value_authority": "slave_zero_dual_storage",
            "phase_application": "dual_source_slave_zero_no_phase_reapplication",
        }
    )
    dual_observed = complex(
        np.nextafter(float(np.real(dual_value_expected)), np.inf),
        float(np.imag(dual_value_expected)),
    )
    source_errors = []
    source_gates = []
    dual_metrics = _check_source_packets(
        "source_dual", {dual_key: dual_observed}, dual_facts, seed,
        source_errors, source_gates,
    )
    assert source_errors == []
    assert source_gates == []
    assert dual_metrics["independent_source_exact_mismatch_count"] == 1
    assert dual_metrics["independent_source_relative"] <= 1.0e-13
    assert dual_metrics["independent_source_max_abs"] <= 1.0e-12

    base_key = ((1, 2, 3), (4, 5, 6))
    primal_value = 1.75 - 0.5j
    dual_value = -0.25 + 2.0j
    packets = {
        label: {
            (role, 1, base_key, 0, ("canonical",), None, (1.0, 0.0)): value
        }
        for label, role in PACKET_ROLES.items()
        for value in (
            primal_value if label in {"source_primal", "projected_primal", "projected_repeat_primal"}
            else SOURCE2_SCALE * primal_value if label == "projected_scaled_primal"
            else ALPHA * primal_value + BETA * SOURCE2_SCALE * primal_value if label == "projected_combo_primal"
            else dual_value,
        )
    }
    work = np.conjugate(dual_value) * primal_value
    assert work == -1.4375 - 3.375j
    assert work.imag < 0.0
    transfer_facts = {
        "pair_fine_to_coarse": [3, 1],
        "primal_output_finite": True,
        "dual_output_finite": True,
        "primal_repeat_relative": 0.0,
        "adjoint_repeat_relative": 0.0,
        "linearity_relative": 0.0,
        "input_unchanged": True,
        "global_work_lhs": [float(work.real), float(work.imag)],
        "global_work_rhs": [float(work.real), float(work.imag)],
        "explicit_work_rhs": [float(work.real), float(work.imag)],
        "global_adjoint_work_relative": 0.0,
        "explicit_adjoint_work_relative": 0.0,
        "implemented_vs_explicit_vector_relative": 0.0,
        "phase_application_primal": "finalized_floquet_mpc_once",
        "phase_application_adjoint": "fine_dual_homogenize_then_coarse_C^H_once",
        "coarse_dual_reduction": "C^H_once",
        "source_finite": True,
        "source_nonzero": True,
    }
    errors: list[str] = []
    gates: list[str] = []
    metrics = _check_packet_relations(packets, transfer_facts, errors, gates)
    assert errors == []
    assert gates == []
    assert metrics["canonical_explicit_adjoint_work_relative"] == 0.0
    assert metrics["global_adjoint_work_relative"] == 0.0
    assert metrics["canonical_work_lhs"] == [-1.4375, -3.375]
    assert metrics["canonical_work_rhs"] == [-1.4375, -3.375]

    missing = dict(packets)
    missing["projected_scaled_primal"] = {}
    errors = []
    gates = []
    _check_packet_relations(missing, transfer_facts, errors, gates)
    assert errors == []
    assert any("scaled primal relation failed" in item for item in gates)

    bad_global = dict(transfer_facts)
    bad_global["global_work_rhs"] = [float((work + 1.0).real), float((work + 1.0).imag)]
    bad_global["global_adjoint_work_relative"] = _scalar_relative(work, work + 1.0)
    errors = []
    gates = []
    _check_packet_relations(packets, bad_global, errors, gates)
    assert errors == []
    assert "C0 global adjoint work failed" in gates
    assert _scalar_relative(work, work) == 0.0
