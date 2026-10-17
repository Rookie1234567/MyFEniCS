from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from src.solvers import task41_b0_mode_inventory as inventory


def _abi_facts(identity):
    return {
        "profile_identity": identity["profile_identity"],
        "runtime_profile": identity["runtime_profile"],
        "qualification": identity["abi_qualification"],
        "receipt_sha256": identity["abi_receipt_sha256"],
        "scalar": identity["scalar"],
        "integer": identity["integer"],
        "mpi_size": identity["mpi_size"],
    }


@pytest.mark.parametrize("index", [0, 1])
def test_task41_b0_manifest_identity_resolves_exact_qualified_receipt(index):
    identity = inventory.TASK41_B0_MODE_MANIFEST_IDENTITIES[index]

    assert inventory.resolve_task41_b0_mode_manifest_identity(_abi_facts(identity)) == dict(
        identity
    )


def test_task41_b0_manifest_identity_rejects_unknown_abi_receipt():
    identity = inventory.TASK41_B0_MODE_MANIFEST_IDENTITIES[1]
    abi_facts = _abi_facts(identity)
    abi_facts["receipt_sha256"] = "f" * 64

    with pytest.raises(ValueError, match="no registered identity"):
        inventory.resolve_task41_b0_mode_manifest_identity(abi_facts)


def test_task41_b0_manifest_identity_comparison_evidence_is_hash_bound():
    identity = inventory.TASK41_B0_MODE_MANIFEST_IDENTITIES[1]
    repository_root = Path(__file__).resolve().parents[2]
    evidence_path = repository_root / identity["comparison_evidence_path"]

    assert hashlib.sha256(evidence_path.read_bytes()).hexdigest() == identity[
        "comparison_evidence_sha256"
    ]


def test_task41_b0_q_counts_match_compact_saved_mode_evidence_and_alias_rule():
    repository_root = Path(__file__).resolve().parents[2]
    evidence_path = repository_root / inventory.TASK41_B0_MODE_Q_MAP_EVIDENCE_PATH
    raw = evidence_path.read_bytes()
    evidence = json.loads(raw)
    actual = evidence["actual"]
    q_counts = tuple(actual["q_port_counts"])
    sector_counts = tuple(actual["sector_port_counts"])

    assert hashlib.sha256(raw).hexdigest() == inventory.TASK41_B0_MODE_Q_MAP_EVIDENCE_SHA256
    assert q_counts == inventory.TASK41_B0_EXPECTED_Q_PORT_COUNTS
    assert sector_counts == inventory.TASK41_B0_EXPECTED_SECTOR_PORT_COUNTS
    assert tuple(
        q_counts[sector] + q_counts[sector + 100] for sector in range(100)
    ) == sector_counts
    assert evidence["mapping"]["mapper_equal_to_independent_n_mod_200"] is True
    assert evidence["mapping"]["fe_mesh_built"] is False
    assert evidence["mapping"]["modes_regenerated"] is False
    assert actual["assignment_sha256_int16le"] == (
        inventory.TASK41_B0_MODE_ASSIGNMENT_SHA256_INT16LE
    )
    assert evidence["rejected_historical_expectation"][
        "actual_q_vector_differences"
    ] == 141
    assert evidence["rejected_historical_expectation"][
        "actual_sector_vector_differences"
    ] == 100
    for identity in inventory.TASK41_B0_MODE_MANIFEST_IDENTITIES:
        assert identity["mode_assignment_sha256_int16le"] == (
            inventory.TASK41_B0_MODE_ASSIGNMENT_SHA256_INT16LE
        )
        assert identity["q_map_evidence_sha256"] == (
            inventory.TASK41_B0_MODE_Q_MAP_EVIDENCE_SHA256
        )


def test_task41_b0_inventory_rejects_missing_modes_before_building_q_map(monkeypatch):
    identity = dict(inventory.TASK41_B0_MODE_MANIFEST_IDENTITIES[1])
    identity.update(
        identity="task41_b0_missing_modes_fixture_v1",
        manifest_sha256=hashlib.sha256(b"[]\n").hexdigest(),
        manifest_bytes=3,
    )
    monkeypatch.setattr(inventory, "TASK41_B0_MODE_MANIFEST_IDENTITIES", (identity,))
    monkeypatch.setattr(inventory, "outgoing_port_modes_3d", lambda _cfg: (object(),))
    monkeypatch.setattr(
        inventory,
        "build_ordered_mode_manifest",
        lambda _modes, _cfg: ((), b"[]\n", identity["manifest_sha256"]),
    )
    monkeypatch.setattr(
        inventory,
        "build_task40_v10_sector_contexts",
        lambda *_args, **_kwargs: pytest.fail("q map must not be built for missing modes"),
    )
    axes = {
        "x": tuple(float(value) for value in range(11)),
        "y": tuple(float(value) for value in range(201)),
        "z": tuple(float(value) for value in range(15)),
    }

    with pytest.raises(ValueError, match="registered ABI-bound identity"):
        inventory.build_task41_b0_mode_inventory(
            object(), axes, abi_facts=_abi_facts(identity)
        )


def test_task41_b0_q_map_failure_records_actual_counts_and_first_mismatch(monkeypatch):
    assignment_digest = hashlib.sha256(np.asarray([58], dtype="<i2").tobytes()).hexdigest()
    identity = dict(inventory.TASK41_B0_MODE_MANIFEST_IDENTITIES[1])
    identity.update(
        identity="task41_b0_map_failure_fixture_v1",
        mode_count=1,
        manifest_sha256=hashlib.sha256(b"[]\n").hexdigest(),
        manifest_bytes=3,
        mode_assignment_sha256_int16le=assignment_digest,
    )
    monkeypatch.setattr(inventory, "TASK41_B0_MODE_MANIFEST_IDENTITIES", (identity,))
    monkeypatch.setattr(inventory, "TASK41_B0_MODE_COUNT", 1)
    monkeypatch.setattr(inventory, "TASK41_B0_EXPECTED_Q_PORT_COUNTS", (0,) * 200)
    monkeypatch.setattr(inventory, "TASK41_B0_EXPECTED_SECTOR_PORT_COUNTS", (0,) * 100)
    monkeypatch.setattr(
        inventory, "outgoing_port_modes_3d", lambda _cfg: (SimpleNamespace(),)
    )
    monkeypatch.setattr(
        inventory,
        "build_ordered_mode_manifest",
        lambda _modes, _cfg: ((), b"[]\n", identity["manifest_sha256"]),
    )
    contexts = []
    for sector in range(100):
        selected = sector == 58
        contexts.append(
            SimpleNamespace(
                global_q_indices=(sector, sector + 100),
                original_mode_indices=np.asarray([0] if selected else [], dtype=np.int64),
                local_branch_indices=np.asarray([0] if selected else [], dtype=np.int8),
            )
        )
    monkeypatch.setattr(
        inventory, "build_task40_v10_sector_contexts", lambda *_args, **_kwargs: contexts
    )
    axes = {
        "x": tuple(float(value) for value in range(11)),
        "y": tuple(float(value) for value in range(201)),
        "z": tuple(float(value) for value in range(15)),
    }

    with pytest.raises(ValueError, match="frozen alias inventory") as error:
        inventory.build_task41_b0_mode_inventory(
            object(), axes, abi_facts=_abi_facts(identity)
        )
    diagnostic = json.loads(str(error.value).split(": ", maxsplit=1)[1])

    assert diagnostic["actual_q_port_counts"][58] == 1
    assert diagnostic["first_q_mismatch"] == {"q": 58, "expected": 0, "actual": 1}
    assert diagnostic["first_sector_mismatch"] == {
        "sector": 58,
        "expected": 0,
        "actual": 1,
    }
    assert diagnostic["assignment_sha256_int16le"] == assignment_digest
