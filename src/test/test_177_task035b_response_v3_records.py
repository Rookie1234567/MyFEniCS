from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
OUTCOMES = (
    ROOT / "docs/task035b_high_order_local_hp_resource_envelope/outcomes"
)
RECORDS = (
    ROOT
    / "benchmarks/cases/095_high_order_local_hp_resource_envelope/records"
)
MANIFEST_PATH = OUTCOMES / "all_candidates.json"
CSV_PATH = OUTCOMES / "all_candidates.csv"

EXPECTED_NEW_RECORD_HASHES = {
    "fixed_p5trace_p6interior_h13_top2_phase_redistribution_mpi8_v1.json": (
        "ff12b909aa1c75dcf15246ba48a8169bf9653d13ddf36709c46367217d799b4b"
    ),
    "fixed_p5trace_p6interior_h14_exact_reverse_h13_top2_mpi8_v1.json": (
        "6036acd898d02967d40299b48957791f0b2ae021338940dc59177eb090bf788b"
    ),
    "physical_selective_trace_execution_capability_v2.json": (
        "e8c0b1d3d758ee1fea71fa261ded1fdfb4946a909437bc4f69aec52975ecf3ef"
    ),
    "h15_factor_free_iterative_mpi8_v1.json": (
        "ce7a7bd6932725987a5d3583df29396a027c661bcc80514f8dd33af5118edc2b"
    ),
    "h15_physical_slab_dtn_iterative_formal_screen_mpi8_v2.json": (
        "8d13e70906fecce6d729491c453c93cc0664a6fa46906a5f1f4d5eb59083d444"
    ),
    "h15_canonical_orientation_symbolic_numeric_cold_warm_mpi8_v2.json": (
        "2f7c2503677fccb81f08d1c640d245f5d58bc497fbeae56df174477f4bfd0678"
    ),
    "h13_canonical_orientation_symbolic_numeric_cold_warm_mpi8_v1.json": (
        "bfc83e13a28018d2751a1dddb4f478cf424788c6725f32b26b964b718d1bcf66"
    ),
}
EXPECTED_NEW_IDS = (
    "c095_h13_top2_phase_redistribution",
    "c095_h14_exact_reverse_h13_top2",
    "c095_physical_selective_trace_execution_capability_v2",
    "c095_h15_factor_free_gmres_jacobi",
    "c095_h15_factor_free_fgmres_asm_ilu",
    "c095_h15_global_factor_free_physical_slab_dtn",
    "c095_h15_setup_canonical_cold",
    "c095_h15_setup_canonical_warm",
    "c095_h13_setup_canonical_cold",
    "c095_h13_setup_canonical_warm",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _by_id() -> dict[str, dict[str, Any]]:
    rows = _manifest()["candidates"]
    return {row["candidate_id"]: row for row in rows}


def test_candidate_manifest_and_csv_have_same_68_unique_rows() -> None:
    manifest = _manifest()
    candidates = manifest["candidates"]
    ids = [row["candidate_id"] for row in candidates]
    with CSV_PATH.open(newline="", encoding="utf-8") as stream:
        csv_rows = list(csv.DictReader(stream))
    csv_ids = [row["candidate_id"] for row in csv_rows]

    assert manifest["schema_version"] == "task035b.all-candidates.v2"
    assert manifest["source_snapshot"] == (
        "cf14e84f4a0f9216b6139a146eba78cdcfd45bb9"
    )
    assert manifest["hybrid_eligible_candidate_count"] == 0
    assert manifest["ordinary_default_changed"] is False
    assert len(candidates) == len(ids) == len(set(ids)) == 68
    assert csv_ids == ids
    assert tuple(ids[-10:]) == EXPECTED_NEW_IDS
    for json_row, csv_row in zip(candidates[-10:], csv_rows[-10:], strict=True):
        assert Path(json_row["record"]).name == csv_row["record"]


def test_new_candidate_records_are_hash_bound() -> None:
    rows = _by_id()
    for filename, expected_hash in EXPECTED_NEW_RECORD_HASHES.items():
        assert _sha256(RECORDS / filename) == expected_hash
    for candidate_id in EXPECTED_NEW_IDS:
        row = rows[candidate_id]
        filename = Path(row["record"]).name
        assert row["record_sha256"] == EXPECTED_NEW_RECORD_HASHES[filename]


def test_accuracy_setup_and_iterative_authorities_remain_separate() -> None:
    rows = _by_id()
    best = rows["c095_fixed_h13_z"]
    assert best["resources"] == [89740, 20120, 11013212, 36273200]
    assert "10/12 power and 10/12 amplitude" in best["accuracy_gate"]

    h13_cold = rows["c095_h13_setup_canonical_cold"]
    assert h13_cold["resources"] == [89740, 20120, 11014172, 35746600]
    assert "no 2x cold-code claim" in h13_cold["accuracy_gate"]
    assert "significant-channel audit in setup profile" in h13_cold[
        "unavailable"
    ]

    for candidate_id in (
        "c095_h15_factor_free_gmres_jacobi",
        "c095_h15_factor_free_fgmres_asm_ilu",
        "c095_h15_global_factor_free_physical_slab_dtn",
    ):
        row = rows[candidate_id]
        assert row["classification"] == "controlled_negative"
        assert "no official outputs" in row["accuracy_gate"]
        assert "Hybrid eligibility" in row["unavailable"]


def test_records_do_not_promote_projection_fixture_or_failed_ksp() -> None:
    h14 = json.loads(
        (
            RECORDS
            / "fixed_p5trace_p6interior_h14_exact_reverse_h13_top2_mpi8_v1.json"
        ).read_text(encoding="utf-8")
    )
    assert h14["diffraction_channel_comparison"][
        "significant_power_pass_count"
    ] == 7
    assert h14["diffraction_channel_comparison"][
        "significant_complex_amplitude_pass_count"
    ] == 8
    assert h14["candidate_accuracy_pass"] is False

    capability = json.loads(
        (
            RECORDS / "physical_selective_trace_execution_capability_v2.json"
        ).read_text(encoding="utf-8")
    )
    boundary = capability["formal_accuracy_boundary"]
    assert boundary["actual_channel_dwr_selection"] is False
    assert boundary["runner_wired"] is False
    assert boundary["selective_candidate_count"] == 0
    assert boundary["selective_pde_run_count"] == 0
    assert boundary["hybrid_eligible"] is False

    legacy_iterative = json.loads(
        (RECORDS / "h15_factor_free_iterative_mpi8_v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert all(
        profile["official_result"] is False
        and profile["full_recovered_true_residual"] > 1.0e-9
        for profile in legacy_iterative["profiles"]
    )
    physical_iterative = json.loads(
        (
            RECORDS
            / "h15_physical_slab_dtn_iterative_formal_screen_mpi8_v2.json"
        ).read_text(encoding="utf-8")
    )
    assert physical_iterative["profile"]["strictly_factorless"] is False
    assert physical_iterative["formal_screen"]["ksp_converged"] is False
    assert physical_iterative["official_output_authority"][
        "official_result"
    ] is False
