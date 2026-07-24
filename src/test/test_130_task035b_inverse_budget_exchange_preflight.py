from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path

import pytest

from benchmarks.task035b_inverse_budget_exchange_preflight import (
    DEFAULT_OUTPUT,
    _is_full_sha,
    _resolve_output,
    _write_json_exclusive,
    build_preflight_record,
)
from src.adaptivity.inverse_trace_interior_budget_audit import (
    audit_inverse_trace_interior_budget_exchange,
    audit_trace_interior_pair,
)


@lru_cache(maxsize=1)
def _audit() -> dict:
    return audit_inverse_trace_interior_budget_exchange()


def test_p6_trace_p5_interior_fails_exact_sequence() -> None:
    pair = _audit()["inverse_budget_exchange_pairs"][
        "p6_trace_p5_cell_interior"
    ]
    exact = pair["exact_sequence"]
    assert pair["mixed_vector_space_dimension"] == 672
    assert pair["trace_dimension"] == 432
    assert pair["cell_interior_dimension"] == 240
    assert pair["cell_interior_modes_removed_from_full_trace_degree_space"] == 210
    assert exact["measured_curl_rank"] == 492
    assert exact["measured_curl_nullity"] == 180
    assert exact["expected_nonconstant_gradient_dimension"] == 281
    assert exact["missing_gradient_mode_count"] == 101
    assert exact["pass"] is False
    assert pair["audit_completed"] is True
    assert pair["pass"] is False
    assert pair["candidate_authorized"] is False
    assert pair["pde_authorized"] is False


def test_p6_trace_p4_interior_fails_exact_sequence() -> None:
    pair = _audit()["inverse_budget_exchange_pairs"][
        "p6_trace_p4_cell_interior"
    ]
    exact = pair["exact_sequence"]
    assert pair["mixed_vector_space_dimension"] == 540
    assert pair["trace_dimension"] == 432
    assert pair["cell_interior_dimension"] == 108
    assert pair["cell_interior_modes_removed_from_full_trace_degree_space"] == 342
    assert exact["measured_curl_rank"] == 445
    assert exact["measured_curl_nullity"] == 95
    assert exact["expected_nonconstant_gradient_dimension"] == 244
    assert exact["missing_gradient_mode_count"] == 149
    assert exact["pass"] is False
    assert pair["audit_completed"] is True
    assert pair["pass"] is False
    assert pair["candidate_authorized"] is False
    assert pair["pde_authorized"] is False


def test_p5_trace_controls_close_exact_sequence() -> None:
    controls = _audit()["qualified_p5_trace_controls"]
    p5 = controls["p5_trace_p5_cell_interior"]
    p6 = controls["p5_trace_p6_cell_interior"]

    assert p5["mixed_vector_space_dimension"] == 540
    assert p5["trace_dimension"] == 300
    assert p5["cell_interior_dimension"] == 240
    assert p5["exact_sequence"]["measured_curl_rank"] == 325
    assert p5["exact_sequence"]["measured_curl_nullity"] == 215
    assert (
        p5["exact_sequence"]["expected_nonconstant_gradient_dimension"]
        == 215
    )
    assert p5["exact_sequence"]["missing_gradient_mode_count"] == 0
    assert p5["audit_completed"] is True
    assert p5["pass"] is True
    assert p5["exact_sequence_pass"] is True

    assert p6["mixed_vector_space_dimension"] == 750
    assert p6["trace_dimension"] == 300
    assert p6["cell_interior_dimension"] == 450
    assert p6["exact_sequence"]["measured_curl_rank"] == 474
    assert p6["exact_sequence"]["measured_curl_nullity"] == 276
    assert (
        p6["exact_sequence"]["expected_nonconstant_gradient_dimension"]
        == 276
    )
    assert p6["exact_sequence"]["missing_gradient_mode_count"] == 0
    assert p6["audit_completed"] is True
    assert p6["pass"] is True
    assert p6["exact_sequence_pass"] is True


def test_preflight_is_controlled_negative_without_candidate_or_pde() -> None:
    record = build_preflight_record(
        source_identity={
            "commit_sha": "a" * 40,
            "verified_clean_sha": "a" * 40,
            "branch": "test",
        },
        environment_identity={"checks": {"test": True}},
    )
    assert record["pass"] is True
    assert record["controlled_negative"] is True
    assert record["candidate_count"] == 0
    assert record["candidate_authorized"] is False
    assert record["pde_run_count"] == 0
    assert record["pde_authorized"] is False
    assert record["ordinary_default_changed"] is False
    assert record["execution_scope"]["mesh_built"] is False
    assert record["execution_scope"]["form_compiled"] is False
    assert record["execution_scope"]["matrix_assembled"] is False
    assert record["execution_scope"]["pde_run"] is False


def test_pair_audit_rejects_unsupported_degrees() -> None:
    with pytest.raises(ValueError, match="trace_degree"):
        audit_trace_interior_pair(7, 5)
    with pytest.raises(ValueError, match="cell_interior_degree"):
        audit_trace_interior_pair(6, 0)


def test_clean_sha_shape_and_exclusive_output(tmp_path: Path) -> None:
    assert _is_full_sha("A" * 40)
    assert not _is_full_sha("a" * 39)
    assert not _is_full_sha("g" * 40)

    output = tmp_path / "nested" / "preflight.json"
    payload = {"status": "controlled_negative", "pass": True}
    _write_json_exclusive(output, payload)
    assert json.loads(output.read_text(encoding="utf-8")) == payload
    with pytest.raises(FileExistsError):
        _write_json_exclusive(output, payload)


def test_default_output_is_tracked_and_external_override_is_rejected(
    tmp_path: Path,
) -> None:
    resolved = _resolve_output(DEFAULT_OUTPUT)
    assert resolved.name == (
        "inverse_trace_interior_budget_exchange_preflight.json"
    )
    assert "095_high_order_local_hp_resource_envelope/records" in str(
        resolved
    )
    with pytest.raises(ValueError, match="must remain in Case095 records"):
        _resolve_output(tmp_path / "external.json")
