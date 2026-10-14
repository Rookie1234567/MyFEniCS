from __future__ import annotations

import json
from types import SimpleNamespace
from pathlib import Path

import numpy as np
import pytest
from scipy import sparse

from src.solvers.task40_v10_p6_yorbit import (
    Q_ASSEMBLY_LEGACY,
    _task40_v30_load_sector_q_csr_pair,
    _task40_v30_ordered_mode_key_sha256,
    assemble_task40_v10_selected_sector_blocks,
)


def test_selected_twist_assembly_builds_only_the_requested_global_q():
    class Coordinates:
        def q_map(self, branch, *, allocation_gate):
            allocation_gate("map", {"additional_payload_bytes": 0, "workspace_bytes": 0})
            column = np.zeros(4, dtype=np.complex128)
            column[branch] = 1.0
            return sparse.csr_matrix(column.reshape(4, 1))

    class Action:
        def __init__(self):
            self.iterations = 0

        def iter_reduced_contributions(self, *, allocation_gate):
            self.iterations += 1
            yield (
                np.arange(4, dtype=np.int32),
                np.arange(4, dtype=np.int32),
                np.diag(np.asarray([2.0, 7.0, 11.0, 13.0], dtype=np.complex128)),
                "fixture/diagonal",
            )

    action = Action()
    matrices, audit = assemble_task40_v10_selected_sector_blocks(
        action,
        Coordinates(),
        SimpleNamespace(global_q_indices=(0, 4), twist_index=0),
        selected_global_q_indices=(4,),
        allocation_gate=lambda *_args: None,
        assembly_strategy=Q_ASSEMBLY_LEGACY,
    )

    assert set(matrices) == {4}
    assert matrices[4].shape == (1, 1)
    assert matrices[4].toarray()[0, 0] == 7.0 + 0.0j
    assert audit["unselected_q_csr_rebuilt"] is False
    assert audit["fourier_diagonalization_gate"] == "DEFERRED_TO_NATIVE_QUALIFICATION"
    assert action.iterations == 1


def test_v32_worker_handoff_requires_both_saved_map_audits():
    from src.runners.task40_v10_worker import _task40_v32_owner_bound_q_maps

    q_maps = {0: object(), 4: object()}
    owner = {
        "q_maps_by_q": q_maps,
        "owner_receipt": {
            "saved_q0_q4_map_binding": {
                "q0": {"passed": True},
                "q4": {"passed": True},
            }
        },
    }

    assert _task40_v32_owner_bound_q_maps({"review_version": "V31"}, owner) is None
    assert _task40_v32_owner_bound_q_maps({"review_version": "V32"}, owner) is q_maps

    owner["owner_receipt"]["saved_q0_q4_map_binding"]["q4"]["passed"] = False
    with pytest.raises(ValueError, match="passing saved q0/q4 binding audit"):
        _task40_v32_owner_bound_q_maps({"review_version": "V32"}, owner)


def test_v30_sector_adapter_binds_actual_twist_maps_h_modes_and_q0_lookup():
    mode = SimpleNamespace(side="bottom", m=0, n=0, polarization="s")

    class Profile:
        name = "fixture-profile"

        def identity(self):
            return {"name": self.name, "q_count": 8}

    class Coordinates:
        def q_map(self, branch, *, allocation_gate):
            value = np.zeros(4, dtype=np.complex128)
            value[branch] = 1.0
            return sparse.csr_matrix(value.reshape(4, 1))

    class Provider:
        profile = "fixture-profile"
        entries = {q: {} for q in range(8)}

        def __init__(self):
            self.calls = []

        def load(self, q_index, twist_index, **kwargs):
            self.calls.append((q_index, twist_index, kwargs))
            return sparse.csr_matrix(np.asarray([[q_index + 1j]], dtype=np.complex128)), {
                "q_index": q_index,
                "twist_index": twist_index,
                "csr_manifest_sha256": f"{q_index + 1:064x}",
                "native_qualification_sha256": f"{q_index + 9:064x}",
                "qualification_kind": (
                    "LEGACY_QUALIFICATION_IMPORTED_OPERATOR_BINDINGS_DERIVED"
                    if q_index == 0
                    else "V30_NATIVE_PASS"
                ),
                "qualification_status": "PASS",
            }

    condensed = SimpleNamespace(
        full_rows=4,
        trace_constraints=SimpleNamespace(original_to_active={0: 0, 2: 1}),
    )
    action = SimpleNamespace(condensed=condensed)
    bundle = {"mode_sha256": "3" * 64, "modes": (mode,)}
    expected_legacy = {
        "input_sha256": "1" * 64,
        "physical_model_sha256": "6" * 64,
        "mode_manifest_sha256": "3" * 64,
    }
    runtime_identity = {
        "scientific_input_sha256": "1" * 64,
        "ordered_mode_key_sha256": _task40_v30_ordered_mode_key_sha256((mode,)),
        "execution_identity": {"source_sha": "2" * 40, "window_sha256": "5" * 64},
        "legacy_q0_identity": expected_legacy,
    }
    provider = Provider()
    matrices, audit = _task40_v30_load_sector_q_csr_pair(
        provider,
        action=action,
        coordinates=Coordinates(),
        context=SimpleNamespace(twist_index=0, global_q_indices=(0, 4)),
        local_h=np.asarray([1.0, 2.0], dtype=np.float64),
        profile=Profile(),
        global_bundle=bundle,
        mode_inventory=((mode,), ({"mode_index": 0},), "3" * 64),
        runtime_identity=runtime_identity,
        allocation_gate=lambda *_args: None,
    )

    assert set(matrices) == {0, 4}
    assert [(q, twist) for q, twist, _ in provider.calls] == [(0, 0), (4, 0)]
    assert provider.calls[0][2]["expected_operator_identity"]["ordered_mode_sha256"] == (
        runtime_identity["ordered_mode_key_sha256"]
    )
    assert provider.calls[0][2]["expected_q0_active_lookup"].tolist() == [0, -1, 1, -1]
    assert provider.calls[1][2]["expected_q0_active_lookup"] is None
    assert audit["native_operator_requalification_performed"] is False
    assert [row["q_index"] for row in audit["qualification_receipts"]] == [0, 4]
    assert [row["qualification_kind"] for row in audit["qualification_receipts"]] == [
        "LEGACY_QUALIFICATION_IMPORTED_OPERATOR_BINDINGS_DERIVED",
        "V30_NATIVE_PASS",
    ]


def _v30_service_payload(tmp_path):
    from src.geometry.task40_nonseparable_plan import (
        TASK40_COMPARISON_GROUP,
        TASK40_FACTOR_LIFECYCLE_ALL_Q_RESIDENT,
        TASK40_Q_ASSEMBLY_ROW_TILE_V17,
        TASK40_V15_REFERENCE_PC_STRATEGY,
    )
    from src.solvers.task40_v20_registry import task40_v20_case

    case = task40_v20_case(profile="task40extra_v20_p6_y_orbit_target_original_ny8_v1")
    return {
        "run_id": case.run_id,
        "comparison_group": TASK40_COMPARISON_GROUP,
        "method": {"kind": "full3d_iterative"},
        "solver": {
            "preconditioner": case.profile,
            "stage": case.solver_stage,
            "task40_reference_pc_strategy": TASK40_V15_REFERENCE_PC_STRATEGY,
            "task40_q_assembly_strategy": TASK40_Q_ASSEMBLY_ROW_TILE_V17,
            "task40_factor_lifecycle_strategy": TASK40_FACTOR_LIFECYCLE_ALL_Q_RESIDENT,
        },
        "derived": {"physical_intermediate_profile": {"identity": case.profile}},
        "execution": {
            "task40_execution_stop_stage": "full",
            "task40_target_heavy_authorized": True,
            "task40_v30_q_csr_binding": {
                "schema": "task40extra.review_v30_q_csr_worker_binding.v1",
                "selector_path": "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v30_wsl/selector.json",
                "selector_sha256": "a" * 64,
            },
            "task40_v30_factor_bank_config": {
                "schema": "task40extra.review_v30_all_q_factor_bank.v1",
                "require_two_strict_rhs": True,
                "second_rhs_formula": "frozen_formula",
                "output_directory": str(tmp_path / "all_q_packets"),
            },
        },
    }


def test_v30_dispatcher_routes_to_reviewed_service(monkeypatch, tmp_path):
    from src.runners import task40_v20_stage_runner
    from src.runners.task038_full3d_iterative import run_full3d_iterative

    payload = _v30_service_payload(tmp_path)
    calls = []
    monkeypatch.setattr(
        task40_v20_stage_runner,
        "run_task40_v20_stage",
        lambda resolved, directory, *, source_sha: calls.append(
            (resolved, directory, source_sha)
        ) or {"routed": True},
    )

    result = run_full3d_iterative(payload, tmp_path / "run", source_sha="b" * 40)

    assert result == {"routed": True}
    assert len(calls) == 1
    assert calls[0][0] is payload
    assert calls[0][2] == "b" * 40


def test_v30_service_stubs_worker_with_frozen_selector_and_factor_config(monkeypatch, tmp_path):
    from src.runners import task40_v20_stage_runner as runner
    from src.runners import task40_v30_contract

    payload = _v30_service_payload(tmp_path)
    case_profile = payload["solver"]["preconditioner"]
    captured = {}
    contract_sha = "e" * 64
    contract = {
        "execution": {"campaign_window_sha256": "f" * 64},
        "preparation": {
            "accepted_q0_donor": {"identity_sha256": "a" * 64},
            "q_csr_worklist": [{"q": 4, "twist_index": 0}],
            "final_all_q_selector_required_at": "P3_all_q_resident_factor_bank",
        },
    }
    monkeypatch.setenv("TASK40_V30_STRICT_EXECUTION", "1")
    monkeypatch.setenv("TASK40_V30_CONTRACT_PATH", str(tmp_path / "contract.json"))
    monkeypatch.setenv("TASK40_V30_CONTRACT_SHA256", contract_sha)
    monkeypatch.setenv("TASK40_V30_EXECUTION_WINDOW_SHA256", "f" * 64)
    monkeypatch.setattr(
        task40_v30_contract,
        "require_authorized_contract",
        lambda *_args, **_kwargs: (contract, contract_sha),
    )
    monkeypatch.setattr(
        runner,
        "_preflight",
        lambda *_args, **_kwargs: (
            {"run_id": payload["run_id"], "input_sha256": "c" * 64},
            None,
            None,
        ),
    )
    monkeypatch.setattr(
        "src.runners.task40_v10_worker.run_task40_v10_p6_reference_worker",
        lambda resolved, directory, **kwargs: captured.update(
            resolved=resolved, directory=directory, kwargs=kwargs
        ) or {"passed": True, "status": "completed", "official_result": False},
    )

    result = runner.run_task40_v20_stage(
        payload, tmp_path / "attempt", source_sha="d" * 40
    )

    assert result["status"] == "completed"
    assert captured["resolved"] is payload
    assert captured["kwargs"]["profile_identity"] == case_profile
    assert captured["kwargs"]["stop_after_stage"] if "stop_after_stage" in captured["kwargs"] else None is None
    assert captured["kwargs"]["v30_q_csr_binding"] == payload["execution"][
        "task40_v30_q_csr_binding"
    ]
    assert captured["kwargs"]["v30_factor_config"] == payload["execution"][
        "task40_v30_factor_bank_config"
    ]
    receipt_path = Path(tmp_path / "attempt" / "v30_worker_service_receipt.json")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["q_csr_selector"] == payload["execution"]["task40_v30_q_csr_binding"]
    assert receipt["factor_bank_schema"] == payload["execution"][
        "task40_v30_factor_bank_config"
    ]["schema"]
