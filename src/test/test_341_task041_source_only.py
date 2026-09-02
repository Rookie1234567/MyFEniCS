"""Pure contracts for the Task41 source-only loader and input profile."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from benchmarks import task041_source_only as source_only
from benchmarks.task041_source_only import (
    IMPLEMENTATION_FAILURE,
    REFERENCE_SOURCE_SEMANTICS_CHANGED,
    SOURCE_SEMANTICS_UNCHANGED,
    TASK041_CHILD_SCHEMA,
    TASK041_HARD_MEMORY_BYTES,
    TASK041_INPUT,
    TASK041_SOURCE_LABEL,
    TASK041_SURFACE_QUADRATURE_DEGREE,
    SourceOnlyIdentityError,
    classify_reference_relative,
    classify_source_comparison,
    load_verified_shards,
)
from src.io.input_validation import (
    TASK041_HARD_MEMORY_GIB,
    TASK041_MATERIAL_LABEL,
    TASK041_MODEL_ID,
    TASK041_RUN_ID,
    TASK041_TIMEOUT_SECONDS,
    TASK041_WARNING_MEMORY_GIB,
    InputError,
    load_and_resolve,
    simulation_config_3d_from_normalized,
    task041_material_provenance,
    task041_profile_errors,
)
from src.solvers import hybrid_interface_basis

ROOT = Path(__file__).resolve().parents[2]


def test_loader_shape_binds_current_external_descriptor(monkeypatch):
    """The verified loader shape is consumable without changing frozen data."""
    monkeypatch.setattr(
        hybrid_interface_basis,
        "canonical_mode_keys_sha256",
        lambda value: (
            "1" * 64
            if value == keys
            else pytest.fail("key hash did not receive canonical keys")
        ),
    )
    monkeypatch.setattr(
        hybrid_interface_basis,
        "canonical_external_mode_metadata_sha256",
        lambda value: (
            "2" * 64
            if value == beta
            else pytest.fail("metadata hash did not receive full records")
        ),
    )
    keys = [
        {"side": "bottom", "m": index, "n": 0, "polarization": "s"}
        for index in range(296)
    ]
    beta = [
        {
            "side": "bottom",
            "m": index,
            "n": 0,
            "polarization": "s",
            "beta": [1.0, 0.0],
            "propagating": True,
            "rayleigh_warning": False,
        }
        for index in range(296)
    ]
    frozen = {
        "count": 296,
        "canonical_keys": keys,
        "beta_metadata": beta,
        "canonical_key_list_sha256": "1" * 64,
        "resolved_mode_metadata_sha256": "2" * 64,
        "legacy_beta_metadata_sha256": "3" * 64,
        "legacy_beta_metadata_sha256_expected": "3" * 64,
        "index177_key": keys[177],
        "resolved_config_sha256": "f" * 64,
    }
    verified_parent = {
        "identity_preflight": {
            "pass": True,
            "external_mode_authority": frozen,
        }
    }
    loaded = {
        "frozen_descriptor": source_only._extract_frozen_external_mode_descriptor(
            verified_parent
        )
    }
    current, audit = source_only.bind_current_external_mode_authority(
        loaded,
        {"count": 296, "keys": keys, "modes": beta},
        "a" * 64,
    )
    assert current["resolved_config_sha256"] == "a" * 64
    assert current["legacy_beta_metadata_sha256"] == "3" * 64
    assert current["legacy_beta_metadata_sha256_expected"] == "3" * 64
    assert audit["physical_external_inventory_exact"] is True
    assert current["index177_key"] == keys[177]


INPUT = ROOT / TASK041_INPUT


def test_task041_dat_profile_and_reporting_contract() -> None:
    spec = load_and_resolve(INPUT)
    normalized = spec.as_jsonable()
    assert task041_profile_errors(normalized) == []
    runtime_input = dict(normalized)
    runtime_input.pop("derived", None)
    runtime_input.pop("provenance", None)
    runtime_input.pop("schema_version", None)
    runtime_cfg = simulation_config_3d_from_normalized(runtime_input)
    assert runtime_cfg.diffraction_order_max_m is None
    assert runtime_cfg.diffraction_order_max_n is None
    assert runtime_cfg.reporting_diffraction_order_max_m == 25
    assert runtime_cfg.reporting_diffraction_order_max_n == 25
    assert spec.identity["model_id"] == TASK041_MODEL_ID
    assert spec.identity["run_id"] == TASK041_RUN_ID
    assert spec.materials["substrate_name"] == TASK041_MATERIAL_LABEL
    assert spec.materials["grating_name"] == TASK041_MATERIAL_LABEL
    assert tuple(spec.materials["n_substrate"]) == (
        0.99396854453,
        0.00435380777,
    )
    assert tuple(spec.materials["n_grating"]) == (
        0.99396854453,
        0.00435380777,
    )
    assert spec.output["diffraction_order_max_m"] == 25
    assert spec.output["diffraction_order_max_n"] == 25
    assert spec.boundary["dtn_order_policy"] == "auto_propagating"
    assert spec.solver["restart"] == 90
    assert spec.solver["max_iterations"] == 4000
    assert spec.solver["relative_tolerance"] == 5.0e-9
    assert spec.solver["side_residual_correction_steps"] == 1
    assert spec.execution["mpi_size"] == 1
    assert spec.execution["warning_memory_gib"] == TASK041_WARNING_MEMORY_GIB
    assert spec.execution["terminate_memory_gib"] == TASK041_HARD_MEMORY_GIB
    assert (
        spec.execution["absolute_terminate_memory_bytes"] == TASK041_HARD_MEMORY_BYTES
    )
    assert spec.execution["timeout_seconds"] == TASK041_TIMEOUT_SECONDS
    provenance = task041_material_provenance(normalized)
    assert provenance is not None
    assert provenance["material_role"] == "physical W/tungsten material identity"
    assert "extra_residual_correction_steps" not in provenance
    assert "side_residual_correction_steps_public" not in provenance
    assert "correction_semantics" not in provenance
    assert spec.derived["task041_solver_contract"] == {
        "public_side_apply_passes": 1,
        "extra_residual_correction_steps": 0,
        "old_fixed_smoother_refinement": False,
    }
    assert "external_mode_inventory" in spec.derived


def test_task041_unknown_profile_fails_closed(tmp_path: Path) -> None:
    invalid = tmp_path / "unknown.dat"
    invalid.write_text(
        INPUT.read_text(encoding="utf-8").replace(
            'model_id = "task041_5nm_exact_side_hybrid_iterative_p6h4_m480"',
            'model_id = "task041_5nm_unknown_profile"',
        ),
        encoding="utf-8",
    )
    with pytest.raises(InputError):
        load_and_resolve(invalid)


@pytest.mark.parametrize(
    ("needle", "replacement"),
    (
        (
            "requested_modes_per_direction = 480",
            "requested_modes_per_direction = 479",
        ),
        (
            "W / tungsten, 5 nm Task039 authority",
            "not the Task41 authority",
        ),
        (
            "side_residual_correction_steps = 1",
            "side_residual_correction_steps = 2",
        ),
    ),
)
def test_task041_profile_mutations_fail_closed(
    tmp_path: Path, needle: str, replacement: str
) -> None:
    invalid = tmp_path / "invalid.dat"
    source = INPUT.read_text(encoding="utf-8")
    assert needle in source
    invalid.write_text(source.replace(needle, replacement), encoding="utf-8")
    with pytest.raises(InputError):
        load_and_resolve(invalid)


def test_task041_synthetic_eight_shard_hash_loader_and_tamper(tmp_path: Path) -> None:
    declarations: list[dict[str, object]] = []
    keys = [f"physical:{rank}" for rank in range(8)]
    global_key_sha = hashlib.sha256("\n".join(keys).encode("utf-8")).hexdigest()
    for rank, key in enumerate(keys):
        rank_root = tmp_path / f"rank{rank:04d}"
        rank_root.mkdir()
        keys_path = rank_root / "v9_external_dtn_coupling_canonical_keys.json"
        values_path = rank_root / "v9_external_dtn_coupling_canonical_values.npy"
        packet_path = rank_root / "v9_external_dtn_coupling_canonical_packet.json"
        keys_path.write_text(
            json.dumps({"keys": [key]}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        np.save(values_path, np.asarray([rank + 1.0j], dtype=np.complex128))
        packet = {
            "schema": TASK041_CHILD_SCHEMA,
            "side": "bottom",
            "label": TASK041_SOURCE_LABEL,
            "rank": rank,
            "owner_local": True,
            "numeric_allgather": False,
            "full_numeric_replica": False,
            "keys_path": f"rank{rank:04d}/{keys_path.name}",
            "values_path": f"rank{rank:04d}/{values_path.name}",
        }
        packet_path.write_text(
            json.dumps(packet, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        declarations.append(
            {
                **packet,
                "key_count_local": 1,
                "key_sha256": hashlib.sha256(keys_path.read_bytes()).hexdigest(),
                "values_sha256": hashlib.sha256(values_path.read_bytes()).hexdigest(),
                "shard_manifest_sha256": hashlib.sha256(
                    packet_path.read_bytes()
                ).hexdigest(),
                "global_key_set_sha256": global_key_sha,
                "persisted_value_pair_digest_sha256": "synthetic",
                "full_numeric_replica": False,
            }
        )
    loaded = load_verified_shards(tmp_path, declarations)
    assert loaded["key_count"] == 8
    assert loaded["global_key_set_sha256"] == global_key_sha
    assert loaded["values"].dtype == np.dtype(np.complex128)
    values_path = (
        tmp_path / "rank0000" / "v9_external_dtn_coupling_canonical_values.npy"
    )
    values_path.write_bytes(values_path.read_bytes() + b"tampered")
    with pytest.raises(SourceOnlyIdentityError):
        load_verified_shards(tmp_path, declarations)


def test_task041_reference_classification_and_fixed_limits() -> None:
    assert classify_reference_relative(0.0) == SOURCE_SEMANTICS_UNCHANGED
    assert classify_reference_relative(2.0e-12) == REFERENCE_SOURCE_SEMANTICS_CHANGED
    assert (
        classify_source_comparison(True, 2.0e-12) == REFERENCE_SOURCE_SEMANTICS_CHANGED
    )
    assert classify_source_comparison(False, 0.0) == IMPLEMENTATION_FAILURE


@pytest.mark.parametrize(
    ("head", "branch", "status"),
    [
        ("0" * 40, "a" * 40, ""),
        (
            "a" * 40,
            "wrong/task41-branch",
            "",
        ),
        (
            "a" * 40,
            source_only.TASK041_EXPECTED_BRANCH,
            " M unrelated.txt",
        ),
    ],
)
def test_repository_identity_fails_closed(monkeypatch, head, branch, status):
    values = {
        ("rev-parse", "HEAD"): head,
        ("branch", "--show-current"): branch,
        ("status", "--porcelain", "--untracked-files=all"): status,
    }

    def fake_git(_repo_root, *args):
        return values[args]

    monkeypatch.setattr(source_only, "_run_local_git", fake_git)
    with pytest.raises(SourceOnlyIdentityError):
        source_only._validate_repository_identity(
            Path("/not-the-live-repository"), "a" * 40
        )


def test_repository_identity_success_records_provenance(monkeypatch):
    expected_sha = "a" * 40
    values = {
        ("rev-parse", "HEAD"): expected_sha,
        ("branch", "--show-current"): source_only.TASK041_EXPECTED_BRANCH,
        ("status", "--porcelain", "--untracked-files=all"): "",
    }

    def fake_git(_repo_root, *args):
        return values[args]

    monkeypatch.setattr(source_only, "_run_local_git", fake_git)
    identity = source_only._validate_repository_identity(
        Path("/not-the-live-repository"), expected_sha
    )
    assert identity == {
        "head": expected_sha,
        "source_sha": expected_sha,
        "branch": source_only.TASK041_EXPECTED_BRANCH,
        "worktree_clean": True,
        "status_scope": "git_porcelain_nonignored_untracked_all",
    }
    assert TASK041_SURFACE_QUADRATURE_DEGREE == 37
    assert IMPLEMENTATION_FAILURE == "IMPLEMENTATION_FAILURE"
