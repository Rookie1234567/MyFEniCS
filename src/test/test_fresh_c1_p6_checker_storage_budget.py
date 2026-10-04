"""Scalar saved-checker budget contracts; no numerical, FE, or solver imports."""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
from unittest import mock

import pytest


SOURCE = Path(__file__).resolve().parents[2] / "benchmarks/check_fresh_c1_p6_component.py"


@pytest.fixture(scope="module")
def checker():
    spec = importlib.util.spec_from_file_location("fresh_p6_checker_budget_contract", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def packet(checker, selected=0):
    contract = dict(checker.STORAGE_BUDGET_CONTRACTS[selected])
    return {"schema": checker.WORKER_SCHEMA, "actual_inventory": dict(checker.INVENTORY),
            "storage_budget_contract": contract,
            "snapshot": {"archive_payload_limit_bytes": contract["primitive_export_limit_bytes"]}}


@pytest.mark.parametrize("selected", [0, 1])
def test_only_exact_default_or_explicit_c1a_contract_is_accepted(checker, selected):
    report = packet(checker, selected)
    with mock.patch("builtins.__import__", side_effect=AssertionError("unexpected import")):
        result = checker._storage_budget_contract(report)
    assert result == report["storage_budget_contract"]
    assert result is not report["storage_budget_contract"]
    if selected == 0:
        assert result == {"selector": "legacy_512MiB", "primitive_export_limit_bytes": 512*1024**2,
                          "full_packet_uncompressed_limit_bytes": None, "c1a_raw_budget_mib": None}
    else:
        assert result == {"selector": "c1a_768MiB_v1", "primitive_export_limit_bytes": 768*1024**2,
                          "full_packet_uncompressed_limit_bytes": 1024**3, "c1a_raw_budget_mib": 768}


@pytest.mark.parametrize("selected", [0, 1])
@pytest.mark.parametrize("field", ["selector", "primitive_export_limit_bytes",
                                    "full_packet_uncompressed_limit_bytes", "c1a_raw_budget_mib"])
def test_missing_selected_contract_fields_are_rejected(checker, selected, field):
    report = packet(checker, selected)
    del report["storage_budget_contract"][field]
    with pytest.raises(ValueError, match="exact selected C1a storage"):
        checker._storage_budget_contract(report)


@pytest.mark.parametrize("field,value", [
    ("selector", "arbitrary"), ("primitive_export_limit_bytes", 1024**3),
    ("primitive_export_limit_bytes", 805306368.), ("full_packet_uncompressed_limit_bytes", None),
    ("full_packet_uncompressed_limit_bytes", 1073741824.), ("c1a_raw_budget_mib", 512),
    ("c1a_raw_budget_mib", 768.), ("c1a_raw_budget_mib", True), ("extra_permission", True),
])
def test_arbitrary_expanded_or_type_changed_contracts_are_rejected(checker, field, value):
    report = packet(checker, 1)
    report["storage_budget_contract"][field] = value
    with pytest.raises(ValueError, match="exact selected C1a storage"):
        checker._storage_budget_contract(report)


@pytest.mark.parametrize("selected", [0, 1])
@pytest.mark.parametrize("limit", [None, 0, 1, 536870911, 536870913, 805306367,
                                   805306369, 1073741824, 805306368., True])
def test_snapshot_cap_must_equal_exact_selected_primitive_cap(checker, selected, limit):
    report = packet(checker, selected)
    report["snapshot"]["archive_payload_limit_bytes"] = limit
    with pytest.raises(ValueError, match="snapshot primitive cap"):
        checker._storage_budget_contract(report)


def test_default_contract_cannot_borrow_extended_snapshot_cap(checker):
    report = packet(checker)
    report["snapshot"]["archive_payload_limit_bytes"] = 768*1024**2
    with pytest.raises(ValueError, match="snapshot primitive cap"):
        checker._storage_budget_contract(report)


def test_extended_contract_cannot_relabel_default_snapshot_cap(checker):
    report = packet(checker, 1)
    report["snapshot"]["archive_payload_limit_bytes"] = 512*1024**2
    with pytest.raises(ValueError, match="snapshot primitive cap"):
        checker._storage_budget_contract(report)


@pytest.mark.parametrize("missing", ["storage_budget_contract", "snapshot"])
def test_full_checker_rejects_missing_budget_before_imports_or_arrays(checker, missing):
    report = packet(checker, 1)
    del report[missing]
    events, loads, gates = [], [], []
    with mock.patch("builtins.__import__", side_effect=AssertionError("unexpected import")):
        with pytest.raises(ValueError):
            checker.check_component(report, lambda ref: loads.append(ref),
                allocation_gate=lambda stage, facts: gates.append((stage, facts)),
                checkpoint=lambda stage, facts: events.append((stage, facts)))
    assert not loads and not gates
    assert events[-1][0] == "component_checker_failure"
    assert events[-1][1]["independent_component_pass"] is False


def test_mathematical_limits_are_unchanged(checker):
    assert (checker.ACTION_LIMIT, checker.RESIDUAL_LIMIT, checker.ALGEBRA_LIMIT) == (1.e-11, 1.e-10, 1.e-12)
    before = copy.deepcopy(checker.STORAGE_BUDGET_CONTRACTS)
    checker._storage_budget_contract(packet(checker, 1))
    assert checker.STORAGE_BUDGET_CONTRACTS == before
