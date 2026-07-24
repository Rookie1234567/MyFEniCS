"""Tests for the pure-artifact Task035b DtN-port phase audit."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from src.adaptivity.dtn_port_phase_authority import (
    AuthorityValidationError,
    build_dtn_port_phase_authority,
    default_authority_manifest,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return _sha256(path)


def test_default_phase_authority_is_sha_bound_and_passes() -> None:
    record = build_dtn_port_phase_authority(REPO_ROOT)

    assert record["status"] == "artifact_convention_consistency_pass"
    assert record["pass"] is True
    assert len(record["authorities"]) == 4
    assert {
        authority["sample_id"] for authority in record["authorities"]
    } == {
        "p6_h10",
        "p5_h15",
        "p6_h15",
        "fixed_p5trace_p6interior_h15",
    }
    assert all(audit["pass"] for audit in record["source_audits"])
    assert record["cross_artifact_audit"]["pass"] is True
    assert (
        record["root_cause_decision"]["classification"]
        == "no_artifact_level_convention_mismatch_found"
    )
    assert (
        record["root_cause_decision"][
            "common_mode_physical_convention_error_excluded"
        ]
        is False
    )
    assert {
        item["status"] for item in record["not_observable"]
    } == {"not_observable"}
    assert {
        item["item"] for item in record["not_observable"]
    } >= {
        "physical_correctness_of_top_bottom_outgoing_sign",
        "absolute_modal_basis_phase_normalization",
        "dtn_evanescent_buffer_convergence",
    }


def test_compact_record_sha_mismatch_fails_closed() -> None:
    manifest = default_authority_manifest()
    manifest["sources"][0]["record_sha256"] = "0" * 64

    with pytest.raises(
        AuthorityValidationError,
        match="compact record SHA mismatch",
    ):
        build_dtn_port_phase_authority(REPO_ROOT, manifest=manifest)


def test_raw_order_sha_mismatch_fails_closed() -> None:
    manifest = default_authority_manifest()
    manifest["sources"][0]["raw_sha256"] = "0" * 64

    with pytest.raises(
        AuthorityValidationError,
        match="raw order SHA mismatch",
    ):
        build_dtn_port_phase_authority(REPO_ROOT, manifest=manifest)


def test_identity_mismatch_fails_closed() -> None:
    manifest = default_authority_manifest()
    manifest["sources"][0]["record_expectations"][
        "target_identity.geometry"
    ] = "invented irregular geometry"

    with pytest.raises(
        AuthorityValidationError,
        match="identity mismatch",
    ):
        build_dtn_port_phase_authority(REPO_ROOT, manifest=manifest)


def test_artifact_phase_mismatch_is_preserved_as_negative(
    tmp_path: Path,
) -> None:
    manifest = default_authority_manifest()
    source = deepcopy(manifest["sources"][0])
    original_record = json.loads(
        (REPO_ROOT / source["record_path"]).read_text(encoding="utf-8")
    )
    original_raw_dir = Path(
        original_record["raw_evidence"]["run_directory"]
    )
    original_raw_path = (
        REPO_ROOT
        / original_raw_dir
        / source["raw_relative_to_run_directory"]
    )
    modified_raw = json.loads(original_raw_path.read_text(encoding="utf-8"))
    modified_raw["orders"][0]["boundary_phase"][0] += 0.25

    synthetic_root = tmp_path / "repo"
    record_relative = Path("records/source.json")
    raw_directory = Path("raw/source")
    raw_relative = raw_directory / source["raw_relative_to_run_directory"]
    original_record["raw_evidence"]["run_directory"] = str(raw_directory)
    source["record_path"] = str(record_relative)
    source["record_sha256"] = _write_json(
        synthetic_root / record_relative,
        original_record,
    )
    source["raw_sha256"] = _write_json(
        synthetic_root / raw_relative,
        modified_raw,
    )
    manifest["sources"] = [deepcopy(source) for _ in range(4)]
    expected_ids = [
        "p6_h10",
        "p5_h15",
        "p6_h15",
        "fixed_p5trace_p6interior_h15",
    ]
    for sample_id, cloned in zip(
        expected_ids,
        manifest["sources"],
        strict=True,
    ):
        cloned["sample_id"] = sample_id

    record = build_dtn_port_phase_authority(
        synthetic_root,
        manifest=manifest,
    )

    assert record["status"] == "artifact_convention_inconsistency"
    assert record["pass"] is False
    assert any(
        check["name"] == "reference_plane_phase_exp_i_kz_z"
        and check["status"] == "artifact_mismatch"
        for check in record["source_audits"][0]["checks"]
    )
