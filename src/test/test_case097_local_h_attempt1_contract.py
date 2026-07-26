from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RECORDS = (
    ROOT
    / "benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity"
    / "records"
)
SOURCE_SHA = "b12b1887ca3acb534f36186c93e9e5efb10cf2ad"


def _load(name: str) -> dict:
    return json.loads((RECORDS / name).read_text(encoding="utf-8"))


def _sha256(name: str) -> str:
    return hashlib.sha256((RECORDS / name).read_bytes()).hexdigest()


def test_local_h_attempt1_mpi_records_preserve_one_physical_identity() -> None:
    names = (
        "local_h_attempt1_mpi1_v1.json",
        "local_h_attempt1_mpi2_v1.json",
        "local_h_attempt1_mpi8_v1.json",
    )
    rows = tuple(_load(name) for name in names)
    assert {row["mpi_size"] for row in rows} == {1, 2, 8}
    assert all(row["pass"] is True for row in rows)
    assert all(row["source_sha"] == SOURCE_SHA for row in rows)
    assert all(row["heavy_pde_started"] is False for row in rows)
    assert all(row["pde_accuracy_credit"] is False for row in rows)
    assert all(
        row["stable_identity"] == rows[0]["stable_identity"]
        for row in rows[1:]
    )
    assert rows[0]["stable_identity"][
        "canonical_hcurl_restriction_sha256"
    ] == {
        "4": "7c1a37b9f99da5ba01015257afa712d427457eaee1dabb6ff36e6ac62ac14e2b",
        "5": "90bd8eb7c612f044c0026ce0551c2f96d8241adc9b63b8e402652b5b738ccf2a",
        "6": "2ceef9c5827f88e74080a69929687be2b68ea826988417e60f5d5d8899d44a5f",
    }


def test_local_h_attempt1_comparison_is_hash_bound_and_fail_closed() -> None:
    comparison = _load("local_h_attempt1_mpi_identity_v1.json")
    assert comparison["pass"] is True
    assert comparison["status"] == (
        "local_h_attempt1_mpi1_mpi2_mpi8_identity_pass"
    )
    assert comparison["source_sha"] == SOURCE_SHA
    assert comparison["mpi_sizes"] == [1, 2, 8]
    assert comparison["compiled_cell_tensor_binding_complete"] is False
    assert comparison["heavy_pde_started"] is False
    assert comparison["pde_accuracy_credit"] is False
    expected = {
        "local_h_attempt1_mpi1_v1.json": (
            "e652641ff8f7677f235abfe4d3c968032ee41adcc8737dc9c32e782aacba5e63"
        ),
        "local_h_attempt1_mpi2_v1.json": (
            "4682639ca2ff985408231a950bde9686da5edec2504312a864a3b2dce9675c8e"
        ),
        "local_h_attempt1_mpi8_v1.json": (
            "62d3d8f1d61f5055bc2e09f385dc3735c581b24db5b4c4b0cadb21b29ce188d1"
        ),
    }
    assert {_sha256(name) for name in expected} == set(expected.values())
    for row in comparison["input_records"]:
        name = Path(row["path"]).name
        assert row["sha256"] == expected[name]
