from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from benchmarks.task033_case090_pde_core import (
    attach_evidence_sha256,
    evidence_sha256_is_valid,
)
from benchmarks.run_task037_extra_candidate_h import (
    H1R2_CANDIDATE_APPLY_COUNT,
    H1R2_PAYLOAD_LIMIT_BYTES,
    H1R2_REFERENCE_APPLY_COUNT,
    H1R2_SOURCE_LABEL,
    H1R2_TIMEOUT_SECONDS,
    _evaluate_h1r2_worker_qualification,
    _h1r2_numerical_gate,
    _parser,
    _source_definition,
)


def _scope() -> dict:
    return {
        "degree": 6,
        "h_nm": 10.0,
        "mpi_size": 1,
        "global_rows": 4,
        "constraint_count": 1,
        "timeout_seconds": H1R2_TIMEOUT_SECONDS,
        "payload_limit_bytes": H1R2_PAYLOAD_LIMIT_BYTES,
        "source_labels": [H1R2_SOURCE_LABEL],
        "reference_apply_count": H1R2_REFERENCE_APPLY_COUNT,
        "candidate_apply_count": H1R2_CANDIDATE_APPLY_COUNT,
        "field_formulation": "total_field_dtn_port",
        "operator": "A_h=curl-curl-k0^2*epsilon*mass",
        "condensation": False,
        "ksp": False,
        "dtn": False,
        "dtn_surface_term": False,
        "canonical_after_gate": True,
        "ordinary_default_changed": False,
    }


def _candidate_audit() -> dict:
    return {
        "backend": (
            "dolfinx.fem.assemble_vector(existing ndarray, rank-one form)"
            " + vectorized MPC R^H"
        ),
        "form_rank": 1,
        "coefficient_count": 1,
        "apply_count": H1R2_CANDIDATE_APPLY_COUNT,
        "local_owned_rows": 4,
        "local_ghost_rows": 0,
        "local_storage_entries": 4,
        "global_rows": 4,
        "constraint_count": 1,
        "constraint_nnz": 1,
        "constraint_nnz_closes": True,
        "retained_numeric_payload_components": {
            "coefficient_function_local_array_bytes": 720,
            "output_vector_local_storage_bytes": 128,
            "packed_constants_bytes": 64,
            "slave_indices_bytes": 16,
            "owned_slave_indices_bytes": 16,
            "flat_slave_indices_bytes": 16,
            "master_indices_bytes": 16,
            "conjugated_master_coefficients_bytes": 16,
            "constraint_work_bytes": 16,
            "owned_slave_work_bytes": 16,
        },
        "retained_numeric_payload_local_bytes": 1024,
        "retained_numeric_payload_global_sum_bytes": 1024,
        "retained_numeric_payload_global_max_bytes": 1024,
        "global_matrix_materialized": False,
        "global_constraint_matrix_materialized": False,
        "global_condensed_schur_materialized": False,
        "retained_dense_cell_tensor_count": 0,
        "dense_cell_tensor_materialized_per_apply": False,
        "cell_metadata_retained": False,
        "factor_count": 0,
        "ksp_created": False,
        "dtn_used": False,
        "ordinary_default_changed": False,
    }


def _measurement() -> dict:
    cfg = SimpleNamespace(
        wavevector=(1.0 + 0.1j, 0.5 - 0.2j, 0.25 + 0.0j),
        polarization_vector=(1.0 + 0.0j, 0.25 + 0.5j, -0.5 + 0.0j),
        incident_amplitude=1.0 + 0.25j,
    )
    source_definition = _source_definition(H1R2_SOURCE_LABEL, cfg)
    return {
        "label": H1R2_SOURCE_LABEL,
        "source_definition": source_definition,
        "source_definition_sha256": source_definition["definition_sha256"],
        "reference_apply_count": H1R2_REFERENCE_APPLY_COUNT,
        "candidate_apply_count": H1R2_CANDIDATE_APPLY_COUNT,
        "reference_apply_seconds": 1.0,
        "candidate_apply_seconds": 0.5,
        "candidate_repeat_apply_seconds": 1.5,
        "candidate_repeat_apply_count": H1R2_CANDIDATE_APPLY_COUNT,
        "candidate_repeat_equal": True,
        "finite": True,
        "deterministic": True,
        "reference_vs_candidate_relative_error": 1.0e-15,
        "canonical_export": True,
        "candidate_canonical_packet_count": 3,
        "candidate_manifest": {
            "path": "canonical/seed_17037/candidate_manifest.json",
            "sha256": "b" * 64,
            "packet_count": 3,
        },
    }


def _raw_record() -> dict:
    return {
        "schema": "task037.candidate_h.h1r2.worker.v1",
        "scope": _scope(),
        "measurements": [_measurement()],
        "candidate_action_audit": _candidate_audit(),
    }


def test_h1r2_parser_is_fixed_and_does_not_open_scan_controls():
    parser = _parser()
    args = parser.parse_args(["h1r2-worker", "--run-dir", "/tmp/h1r2"])
    assert args.command == "h1r2-worker"
    assert args.run_dir.name == "h1r2"
    assert H1R2_SOURCE_LABEL == "seed_17037"
    assert H1R2_TIMEOUT_SECONDS == 600.0
    assert H1R2_REFERENCE_APPLY_COUNT == 1
    assert H1R2_CANDIDATE_APPLY_COUNT == 2
    assert H1R2_PAYLOAD_LIMIT_BYTES == int(0.50 * 1024**3)
    for name in ("degree", "h_nm", "source", "repeat", "limit", "mpi_size"):
        assert not hasattr(args, name)
    with pytest.raises(SystemExit):
        parser.parse_args(["h1r2-worker", "--run-dir", "/tmp/h1r2", "--degree", "6"])


def test_h1r2_synthetic_worker_record_passes_and_evidence_hashes():
    record = _raw_record()
    qualification = _evaluate_h1r2_worker_qualification(
        record["measurements"],
        record["candidate_action_audit"],
        scope=record["scope"],
    )
    assert qualification["pass"] is True
    assert qualification["status"] == "pass"
    assert qualification["problems"] == []
    attached = attach_evidence_sha256({**record, "qualification": qualification})
    assert evidence_sha256_is_valid(attached)


@pytest.mark.parametrize(
    "mutation",
    (
        "error",
        "determinism",
        "second_timing",
        "payload_closure",
        "payload",
        "dense",
        "candidate_apply_count",
        "source",
        "scope_timeout",
        "scope_operator",
        "canonical_before",
        "canonical_absent",
    ),
)
def test_h1r2_synthetic_gate_rejects_each_representative_mutation(mutation):
    record = deepcopy(_raw_record())
    measurement = record["measurements"][0]
    audit = record["candidate_action_audit"]
    if mutation == "error":
        measurement["reference_vs_candidate_relative_error"] = 1.0e-3
    elif mutation == "determinism":
        measurement["deterministic"] = False
        measurement["candidate_repeat_equal"] = False
    elif mutation == "second_timing":
        measurement["candidate_repeat_apply_seconds"] = 2.1
    elif mutation == "payload_closure":
        audit["retained_numeric_payload_local_bytes"] = 1023
    elif mutation == "payload":
        audit["retained_numeric_payload_global_sum_bytes"] = 0
    elif mutation == "dense":
        audit["retained_dense_cell_tensor_count"] = 1
    elif mutation == "candidate_apply_count":
        audit["apply_count"] = 1
    elif mutation == "source":
        measurement["label"] = "seed_27037"
    elif mutation == "scope_timeout":
        record["scope"]["timeout_seconds"] = 601.0
    elif mutation == "scope_operator":
        record["scope"]["operator"] = "B_h"
    elif mutation == "canonical_before":
        measurement["canonical_export"] = False
    elif mutation == "canonical_absent":
        measurement["canonical_export"] = False
        measurement["candidate_canonical_packet_count"] = None
        measurement["candidate_manifest"] = None
    qualification = _evaluate_h1r2_worker_qualification(
        record["measurements"],
        record["candidate_action_audit"],
        scope=record["scope"],
    )
    assert qualification["pass"] is False
    assert qualification["problems"]


def test_h1r2_numerical_gate_uses_fixed_action_tolerance_and_not_geometry():
    assert _h1r2_numerical_gate(1.0e-11, True, True) is True
    assert _h1r2_numerical_gate(5.0e-11, True, True) is False
    record = _raw_record()
    measurement = record["measurements"][0]
    measurement["reference_vs_candidate_relative_error"] = 5.0e-11
    measurement["canonical_export"] = False
    measurement["candidate_canonical_packet_count"] = None
    measurement["candidate_manifest"] = None
    qualification = _evaluate_h1r2_worker_qualification(
        record["measurements"],
        record["candidate_action_audit"],
        scope=record["scope"],
    )
    assert qualification["pass"] is False
    assert qualification["canonical_checks"]["export_after_numeric_gate"] is True
    assert qualification["canonical_checks"]["manifest_presence"] is True


def test_h1r2_timing_failure_does_not_change_numerical_canonical_gate():
    record = _raw_record()
    record["measurements"][0]["candidate_repeat_apply_seconds"] = 2.1
    qualification = _evaluate_h1r2_worker_qualification(
        record["measurements"],
        record["candidate_action_audit"],
        scope=record["scope"],
    )
    assert qualification["pass"] is False
    assert qualification["canonical_checks"]["export_after_numeric_gate"] is True
    assert qualification["canonical_checks"]["manifest_presence"] is True
