from __future__ import annotations

import hashlib
from pathlib import Path

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
