from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[2]
CASE = ROOT / "benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity"
RECORDS = CASE / "records"


def _load(name: str):
    return json.loads((RECORDS / name).read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_at_commit(commit_sha: str, path: str) -> str:
    completed = subprocess.run(
        ["git", "show", f"{commit_sha}:{path}"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return hashlib.sha256(completed.stdout).hexdigest()


def _commit_is_available(commit_sha: str) -> bool:
    return subprocess.run(
        ["git", "cat-file", "-e", f"{commit_sha}^{{commit}}"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode == 0


def test_case097_manifest_binds_serial_and_real_mpi2_authorities() -> None:
    manifest = _load("compact_authority_v1.json")
    assert manifest["status"] == "case097_phase_a_compact_authority"
    assert manifest["pass"] is True
    assert manifest["record_count"] == 2
    assert manifest["heavy_pde_started"] is False
    assert manifest["ordinary_default_changed"] is False
    for row in manifest["records"]:
        path = RECORDS / row["name"]
        assert _sha256(path) == row["sha256"]
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["schema_version"] == row["schema_version"]
        assert payload["status"] == row["status"]
        assert payload["pass"] is True
        assert payload["source"]["commit_sha"] == manifest[
            "source_commit_sha"
        ]
        assert re.fullmatch(
            r"[0-9a-f]{40}",
            payload["source"]["commit_sha"],
        )
        assert payload["heavy_pde_started"] is False
        for source_path, expected_sha in payload["source"][
            "file_sha256"
        ].items():
            assert source_path
            assert re.fullmatch(r"[0-9a-f]{64}", expected_sha)
            if _commit_is_available(payload["source"]["commit_sha"]):
                assert (
                    _sha256_at_commit(
                        payload["source"]["commit_sha"],
                        source_path,
                    )
                    == expected_sha
                )


def test_case097_entity_catalog_and_all_legal_triples_pass() -> None:
    serial = _load("reference_active_space_authority_v1.json")
    catalog = serial["entity_dof_catalog"]
    assert catalog["status"] == "reference_entity_dof_catalog_pass"
    assert catalog["pass"] is True
    assert catalog["qualified_degrees"] == [4, 5, 6]
    assert catalog["allowed_dimension_degree_triples"] == [
        [4, 4, 4],
        [4, 4, 5],
        [4, 4, 6],
        [4, 5, 5],
        [4, 5, 6],
        [4, 6, 6],
        [5, 5, 5],
        [5, 5, 6],
        [5, 6, 6],
        [6, 6, 6],
    ]
    dimensions = {
        row["degree"]: row["hcurl_dimension"] for row in catalog["degrees"]
    }
    assert dimensions == {4: 300, 5: 540, 6: 882}
    spaces = serial["dimension_uniform_exact_sequence_spaces"]
    assert len(spaces) == 10
    for space in spaces:
        assert space["pass"] is True
        assert (
            space["gradient_rank"]
            == space["expected_nonconstant_gradient_dimension"]
            == space["sampled_curl_nullity"]
        )
        assert space["gradient_embedding_error_max"] <= 5.0e-11
        assert space["curl_gradient_error_max"] <= 2.0e-10
        assert space["hcurl_orientation"]["pass"] is True
        assert space["h1_orientation"]["pass"] is True
    heterogeneous = serial["heterogeneous_entity_space"]
    assert heterogeneous["hcurl_dimension"] == 739
    assert heterogeneous["h1_dimension"] == 266
    assert heterogeneous["hcurl_orientation"]["pass"] is True
    assert heterogeneous["h1_orientation"]["pass"] is True
    assert heterogeneous["h1_orientation"][
        "heterogeneous_custom_basix_T_apply_used"
    ] is False


def test_case097_local_expansion_schur_and_row_reduction_are_measured() -> None:
    serial = _load("reference_active_space_authority_v1.json")
    schur = serial["local_expansion_and_schur"]
    assert schur["status"] == "generalized_local_expansion_and_schur_pass"
    assert schur["projection_relative_error"] <= 2.0e-12
    assert schur["active_recovery_error_max"] <= 1.0e-9
    assert schur["p6_recovery_error_max"] <= 1.0e-9
    assert schur["schur_equation_residual_max"] <= 1.0e-9
    assert schur["audit"]["active_local_rows"] == 738
    assert schur["audit"]["active_trace_rows"] == 288
    assert schur["audit"]["inactive_p6_local_modes"] == 144
    assert schur["audit"]["full_p6_global_matrix_constructed"] is False
    assert schur["audit"]["inactive_p6_rows_globally_numbered"] is False

    fixtures = serial["serial_fixtures"]
    expected = {
        "1x1x1": (738, 288),
        "2x1x1": (1420, 520),
        "2x2x2": (5256, 1656),
    }
    for name, (rows, trace_rows) in expected.items():
        fixture = fixtures[name]
        entity_map = fixture["variable_entity_map"]
        assert entity_map["active_rows"] == rows
        assert entity_map["active_trace_rows"] == trace_rows
        assert entity_map["inactive_modes_globally_numbered"] is False
        assert fixture["variable_condensed_sparsity"]["pass"] is True
        assert (
            fixture["variable_condensed_sparsity"]["structural_nnz"]
            < fixture["uniform_p6_condensed_sparsity"]["structural_nnz"]
        )
        for periodic in ("periodic_x", "periodic_y", "periodic_xy"):
            assert fixture[periodic]["pass"] is True
            assert fixture[periodic]["cycle_closure_error_max"] <= 2.0e-11


def test_case097_mpi2_authority_is_not_a_serial_inference() -> None:
    mpi2 = _load("mpi2_fixture_authority_v1.json")
    assert mpi2["status"] == "task035d_phase_a_mpi2_fixture_pass"
    assert mpi2["environment"]["mpi_size"] == 2
    assert mpi2["rank_identity_match"] is True
    assert len(set(mpi2["rank_identity_sha256"])) == 1
    assert mpi2["owned_cell_count_sum"] == 8
    fixture = mpi2["fixture"]
    assert fixture["variable_entity_map"]["mpi_size"] == 2
    assert fixture["variable_entity_map"]["active_rows"] == 5256
    assert fixture["variable_entity_map"]["active_trace_rows"] == 1656
    assert fixture["uniform_p6_entity_map"]["active_rows"] == 6084
    assert fixture["periodic_xy"]["maximum_orbit_size"] == 4
    assert fixture["periodic_xy"]["independent_periodic_trace_rows"] == 1248
    assert fixture["periodic_xy"]["cycle_closure_error_max"] <= 2.0e-11


def test_case097_scope_keeps_deferred_research_out() -> None:
    config = json.loads((CASE / "config.json").read_text(encoding="utf-8"))
    assert config["ordinary_default_changed"] is False
    assert config["phase_a"]["starts_heavy_pde"] is False
    assert config["out_of_scope"] == {
        "iterative_solver": "not_researched",
        "matrix_free": "not_researched",
        "wavelength_0p7_nm": "not_researched",
        "irregular_geometry": "not_researched",
    }
