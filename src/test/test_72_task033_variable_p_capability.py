from __future__ import annotations

import json

from benchmarks.task033_variable_p_capability import (
    ROOT,
    build_variable_p_capability_audit,
)


def _synthetic_runtime_probe() -> dict:
    return {
        "data_identity": "unit_test_public_symbol_probe",
        "packages": {},
        "symbols": {
            "basix_ufl_mixed_element": {"available": True},
            "ufl_mixed_function_space": {"available": True},
            "dolfinx_mixed_topology_form": {"available": True},
        },
    }


def test_public_mixed_apis_do_not_upgrade_variable_p_hcurl() -> None:
    record = build_variable_p_capability_audit(
        runtime_probe=_synthetic_runtime_probe()
    )
    assert record["status"] == "not_qualified_fail_closed"
    assert not record["decision"]["native_cellwise_variable_p_hcurl_qualified"]
    assert not record["decision"][
        "implement_bespoke_arbitrary_variable_p_constraints"
    ]
    assert all(
        requirement["qualified"] is False
        for requirement in record["semantic_requirements"]
    )


def test_tracked_variable_p_audit_preserves_fail_closed_identity() -> None:
    path = (
        ROOT
        / "benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/"
        "records/variable_p_capability_audit.json"
    )
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["status"] == "not_qualified_fail_closed"
    assert not record["identity"]["is_pde_run"]
    assert not record["identity"]["is_solver_pass"]
    assert not record["identity"]["proves_native_cellwise_variable_p"]
    assert not record["identity"]["ordinary_default_changed"]
