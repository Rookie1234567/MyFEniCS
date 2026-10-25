from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.linalg import lu_factor, lu_solve
from scipy.sparse import csr_matrix

import src.runners.task41_p0_v14_saved_rhs_checker as checker_module
from src.runners.task41_p0_contract import TASK41_B0_V14_SAVED_RHS_CANDIDATE_SCOPE
from src.runners.task41_p0_contract import TASK41_B0_V14_RHS_REFINEMENT_STRATEGY
from src.runners.task41_p0_v14_candidate_io import V14_CELLS, V14_COLUMNS
from src.runners.task41_p0_v14_saved_rhs_candidate import run_v14_saved_candidate
from src.runners.task41_p0_v14_saved_rhs_checker import check_v14_saved_candidate
from src.runners.task41_p0_v4_volume_only_audit import (
    TASK41_P0_V11_METADATA_ACTIVE_ROW,
)


def _ref(label: str, *, shape: tuple[int, ...] = (1,)) -> dict[str, object]:
    digest = hashlib.sha256(label.encode()).hexdigest()
    return {
        "path": f"/synthetic/{label}.npy",
        "name": f"{label}.npy",
        "shape": list(shape),
        "dtype": "complex128",
        "bytes": 16,
        "sha256": digest,
    }


def _synthetic_source(root) -> dict[str, object]:
    n = 450
    diagonal = np.full(n, 3.1 + 0.2j, dtype=np.complex128)
    matrix = np.diag(diagonal)
    lu, pivots = lu_factor(matrix, overwrite_a=False, check_finite=True)
    lu = np.asarray(lu, dtype=np.complex128)
    pivots = np.asarray(pivots, dtype=np.int32)
    trace = np.zeros((1, n), dtype=np.complex128)
    trace[0, 0] = 0.5 - 0.25j
    expansion = csr_matrix(np.asarray([[np.exp(0.73j)]], dtype=np.complex128))
    results_root = root / "results" / "synthetic-model"
    results_root.mkdir(parents=True)
    cells = {}
    for cell in V14_CELLS:
        tensor_ref = _ref(f"cell{cell}_tensor", shape=(451, 451))
        lu_ref = _ref(f"cell{cell}_lu", shape=(n, n))
        local = {
            "cell_index": cell,
            "actual_coordinate_sha256": hashlib.sha256(f"coord-{cell}".encode()).hexdigest(),
            "tensor_ref": tensor_ref,
            "lu_ref": lu_ref,
            "K": matrix,
            "J": trace,
            "LU": lu,
            "pivots": pivots,
            "trace_expansion": expansion,
            "target_active_position": 0,
            "active_ids": np.array([TASK41_P0_V11_METADATA_ACTIVE_ROW], dtype=np.int64),
            "column_terms": {},
        }
        for column in V14_COLUMNS:
            rhs = np.asarray(
                (np.arange(n, dtype=np.float64) + 1.0) * (0.01 + 0.002 * column)
                + 1j * (np.arange(n, dtype=np.float64) * 0.0007 + 0.3),
                dtype=np.complex128,
            )
            old_z = np.asarray(lu_solve((lu, pivots), rhs), dtype=np.complex128)
            old_correction = np.asarray(-(trace @ old_z), dtype=np.complex128)
            s_action = np.array([0.15 + 0.03j * (column + 1) + 0.01 * cell], dtype=np.complex128)
            s_active = np.asarray(expansion.conj().T @ s_action, dtype=np.complex128).reshape(-1)
            old_active = np.asarray(expansion.conj().T @ old_correction, dtype=np.complex128).reshape(-1)
            cell_label = f"cell{cell}_column{column}"
            local["column_terms"][column] = {
                "b_i": rhs,
                "b_i_ref": _ref(cell_label + "_bi", shape=(n,)),
                "old_z_b": old_z,
                "old_z_b_ref": _ref(cell_label + "_zb", shape=(n,)),
                "old_correction": old_correction,
                "old_correction_ref": _ref(cell_label + "_corr"),
                "old_projected_active": old_active,
                "old_projected_active_ref": _ref(cell_label + "_oldactive"),
                "s_action": s_action,
                "s_action_ref": _ref(cell_label + "_s"),
                "s_projected_active": s_active,
                "s_projected_active_ref": _ref(cell_label + "_sactive"),
            }
        cells[cell] = local
    b_t = {0: 0.25 - 0.5j, 1: -0.75 + 0.125j}
    beta = {0: 0.375 - 0.625j, 1: -0.2 + 0.45j}
    y_by_column = {}
    baseline_g_by_column = {}
    report_columns = []
    for column in V14_COLUMNS:
        y = 0.0 + 0.0j
        g = b_t[column]
        for cell in V14_CELLS:
            local = cells[cell]
            term = local["column_terms"][column]
            y += complex(term["s_projected_active"][0])
            g += complex(term["old_projected_active"][0])
        y += beta[column]
        y_by_column[column] = y
        baseline_g_by_column[column] = g
        report_columns.append({
            "column": column,
            "replayed_y9": [y.real, y.imag],
            "replayed_g9_same_lu": [g.real, g.imag],
        })
    return {
        "results_root": results_root,
        "consumer_contract_path": str(root / "synthetic_contract.json"),
        "consumer_contract_sha256": "a" * 64,
        "consumer_contract": {
            "execution_scope": TASK41_B0_V14_SAVED_RHS_CANDIDATE_SCOPE,
            "numerical_strategy": {
                "schema": "task41.p0.b0.internal_rhs_strategy.v2",
                "internal_rhs_strategy": "same_lu_rhs_solve",
                "refinement_strategy": TASK41_B0_V14_RHS_REFINEMENT_STRATEGY,
                "refinement_max_steps": 2,
            },
        },
        "refinement_strategy": TASK41_B0_V14_RHS_REFINEMENT_STRATEGY,
        "refinement_max_steps": 2,
        "consumer_window_sha256": "b" * 64,
        "producer_report_path": root / "frozen_v11.json",
        "producer_report_sha256": "c" * 64,
        "accepted_checker_path": root / "frozen_checker.json",
        "accepted_checker_sha256": "d" * 64,
        "accepted_receipt_path": root / "frozen_receipt.json",
        "accepted_receipt_sha256": "e" * 64,
        "donor_summary_path": root / "frozen_donor.json",
        "donor_summary_sha256": "f" * 64,
        "donor_contract_sha256": "1" * 64,
        "donor_manifest_sha256": "2" * 64,
        "b_t_by_column": b_t,
        "b_t_ref_by_column": {column: _ref(f"native_rhs_{column}", shape=(18501024,)) for column in V14_COLUMNS},
        "b_alpha_by_column": beta,
        "b_alpha_refs_by_column": {
            column: {"rows": _ref(f"beta_rows_{column}", shape=(1,)), "values": _ref(f"beta_values_{column}", shape=(1,))}
            for column in V14_COLUMNS
        },
        "y_by_column": y_by_column,
        "baseline_g_by_column": baseline_g_by_column,
        "report_columns": report_columns,
        "cells": cells,
    }



def _synthetic_saved_star_source(root) -> dict[str, object]:
    source = _synthetic_source(root)
    identity_by_cell = {
        23352: {
            "cell_tag": 2, "permutation": 4680,
            "coordinate_sha256": "00be22d015fe207dd28a8c246380144e51b8ba2d7a3ff63562dfca38b65024e6",
            "selected_local_trace_row": 375,
        },
        23493: {
            "cell_tag": 1, "permutation": 0,
            "coordinate_sha256": "0fbdca58aeb8061e226f1c298a610bbd63f2f43fa15a6830afd3fa435a667ca6",
            "selected_local_trace_row": 75,
        },
    }
    cells = {}
    for old_cell, cell in zip(V14_CELLS, (23352, 23493), strict=True):
        template = source["cells"][old_cell]
        local = dict(template)
        local.update({
            "cell_index": cell,
            "cell_tag": identity_by_cell[cell]["cell_tag"],
            "permutation": identity_by_cell[cell]["permutation"],
            "actual_coordinate_sha256": identity_by_cell[cell]["coordinate_sha256"],
            "active_ids": np.array([4_766_937], dtype=np.int64),
            "target_active_position": 0,
            "matrix_identity": hashlib.sha256(f"star-cell-{cell}".encode()).hexdigest(),
            "column_terms": {},
        })
        for column in V14_COLUMNS:
            old_term = template["column_terms"][column]
            state_terms = {}
            for state in ("j0", "j3"):
                action = np.asarray(old_term["s_action"], dtype=np.complex128).copy()
                if state == "j3":
                    action += np.asarray([0.125 - 0.0625j], dtype=np.complex128)
                state_terms[state] = {
                    "b_i": old_term["b_i"],
                    "b_i_ref": old_term["b_i_ref"],
                    "s_action": action,
                    "s_action_ref": _ref(f"star{cell}_column{column}_{state}_s", shape=(1,)),
                }
            local["column_terms"][column] = {
                "b_i": old_term["b_i"],
                "b_i_ref": old_term["b_i_ref"],
                "old_z_b": None,
                "old_z_b_ref": None,
                "state_terms": state_terms,
            }
        cells[cell] = local

    state_rows = [
        {"column": column, "state": state}
        for column in V14_COLUMNS for state in ("j0", "j3")
    ]
    y_by_column_state = {}
    for state_row in state_rows:
        column, state = state_row["column"], state_row["state"]
        y = 0.0 + 0.0j
        for cell in (23352, 23493):
            local = cells[cell]
            term = local["column_terms"][column]["state_terms"][state]
            projected = np.asarray(
                local["trace_expansion"].conj().T @ term["s_action"], dtype=np.complex128
            ).reshape(-1)
            y += complex(projected[local["target_active_position"]])
        y += complex(source["b_alpha_by_column"][column])
        y_by_column_state[(column, state)] = y
    source.update({
        "stage": "saved_star_extension",
        "cell_order": (23352, 23493),
        "columns": V14_COLUMNS,
        "state_rows": state_rows,
        "target_active_row": 4_766_937,
        "target_original_row": 15_440_235,
        "star_producer_report_path": "/synthetic/v8-star-report.json",
        "star_producer_report_sha256": "1bdd07ac38bce95d58a153bacdca0de6cf5941d08d2706dc127e8b00d8e2764f",
        "star_cell_identities": [
            {"cell_index": cell, **identity_by_cell[cell]}
            for cell in (23352, 23493)
        ],
        "prior_stage_reused": {"candidate_passed_by_decimal": True, "new_getrs_for_reuse": 0},
        "cells": cells,
        "y_by_column_state": y_by_column_state,
    })
    return source

def test_v14_saved_candidate_full_synthetic_entrypoint_and_independent_checker(tmp_path):
    source = _synthetic_source(tmp_path)
    output = source["results_root"] / "synthetic_attempt"
    produced = run_v14_saved_candidate(source=source, output_dir=output)
    report_path = output / "task41_p0_v14_saved_rhs_candidate.json"
    assert produced["path"] == str(report_path)
    assert report_path.is_file()
    assert produced["payload"]["getrs_count"] <= 12
    assert len(produced["payload"]["candidate_rhs"]) == 4
    for row in produced["payload"]["candidate_rhs"]:
        import json
        steps = [json.loads(line) for line in Path(row["initial_and_step_log"]["path"]).read_text().splitlines()]
        assert steps[0]["event"] == "initial"
        assert steps[-1]["event"] == "final"
        assert steps[0]["solved"]["sha256"]
        assert steps[-1]["correction"]["sha256"]
    checked = check_v14_saved_candidate(
        source=source,
        candidate_report_path=report_path,
        candidate_report_sha256=produced["sha256"],
        output_path=source["results_root"] / "synthetic_independent_check.json",
    )
    assert checked["check_completed"] is True
    assert checked["official_result"] is False
    assert checked["scientific_qualified"] is False
    assert checked["scope"]["stage"] == "initial_screen"
    assert checked["conditional_star_coverage_unlocked"] is (checked["candidate_passed"] is True)
    assert len(checked["rhs_checks"]) == 4
    assert {row["state"] for item in checked["rhs_checks"] for row in item["residuals_450_rows"]} >= {"initial", "final"}
    assert any(value != 0j for value in source["b_alpha_by_column"].values())

    # Rewrite both serialized copies of one returned correction, and reseal all
    # nested and outer hashes. The checker must reach the independent -Jz gate.
    candidate = json.loads(report_path.read_text(encoding="utf-8"))
    target = next(
        row for row in candidate["candidate_rhs"]
        if row["cell_index"] == V14_CELLS[0] and row["column"] == V14_COLUMNS[0]
    )
    returned_ref = target["returned_correction"]
    returned_path = Path(returned_ref["path"])
    returned_value = np.load(returned_path, allow_pickle=False)
    contaminated = np.asarray(returned_value + np.asarray([0.25 - 0.125j]), dtype=np.complex128)
    np.save(returned_path, contaminated, allow_pickle=False)

    event_ref = target["initial_and_step_log"]
    event_path = Path(event_ref["path"])
    events = [json.loads(line) for line in event_path.read_text().splitlines()]
    final_correction_ref = events[-1]["correction"]
    final_correction_path = Path(final_correction_ref["path"])
    np.save(final_correction_path, contaminated, allow_pickle=False)

    def reseal(ref):
        path = Path(ref["path"])
        content = path.read_bytes()
        ref["bytes"] = len(content)
        ref["sha256"] = hashlib.sha256(content).hexdigest()

    reseal(returned_ref)
    reseal(final_correction_ref)
    event_path.write_text(
        "".join(json.dumps(event, sort_keys=True) + chr(10) for event in events),
        encoding="utf-8",
    )
    reseal(event_ref)
    report_path.write_text(json.dumps(candidate, sort_keys=True, indent=2) + chr(10), encoding="utf-8")
    tampered_report_sha = hashlib.sha256(report_path.read_bytes()).hexdigest()
    try:
        check_v14_saved_candidate(
            source=source,
            candidate_report_path=report_path,
            candidate_report_sha256=tampered_report_sha,
            output_path=source["results_root"] / "tampered_independent_check.json",
        )
    except ValueError as exc:
        assert "returned correction is not the exact complex128 -J@z output" in str(exc)
    else:
        raise AssertionError("independently inconsistent returned correction was accepted")



def test_v14_saved_star_extension_reuses_shared_rhs_and_checks_same_run_baseline(tmp_path):
    source = _synthetic_saved_star_source(tmp_path)
    output = source["results_root"] / "synthetic_star_attempt"
    produced = run_v14_saved_candidate(source=source, output_dir=output)
    report = produced["payload"]
    assert report["scope"]["stage"] == "saved_star_extension"
    assert report["scope"]["cells"] == [23352, 23493]
    assert report["scope"]["state_rows"] == source["state_rows"]
    assert report["scope"]["full_owner"] is False
    assert report["star_producer_report_sha256"] == source["star_producer_report_sha256"]
    assert len(report["candidate_rhs"]) == 4  # j0 and j3 share each cell/column b_i solve.
    assert report["getrs_count"] <= 12
    assert [
        (row["column"], row["state"])
        for row in report["production_order_rows"]
    ] == [(0, "j0"), (0, "j3"), (1, "j0"), (1, "j3")]
    for row in report["candidate_rhs"]:
        assert row["old_z_b"] is None
        assert row["baseline_mode"] == "same_run_initial_core_solve"
        event_log = [
            json.loads(line)
            for line in Path(row["initial_and_step_log"]["path"]).read_text().splitlines()
        ]
        assert row["baseline_z"] == event_log[0]["solved"]
        assert event_log[0]["initial_getrs_count"] == 1
    check = check_v14_saved_candidate(
        source=source,
        candidate_report_path=produced["path"],
        candidate_report_sha256=produced["sha256"],
        output_path=source["results_root"] / "synthetic_star_check.json",
    )
    assert check["scope"]["stage"] == "saved_star_extension"
    assert check["scope"]["cells"] == [23352, 23493]
    assert check["full_owner_unlocked"] is False
    assert check["conditional_star_coverage_unlocked"] is False
    assert check["saved_coverage_ready"] is (check["candidate_passed"] is True)
    assert len(check["production_order_d_checks"]) == 4
    assert all(item["baseline_mode"] == "same_run_initial_core_solve" for item in check["rhs_checks"])


def test_v14_checker_still_reads_attempt01_without_new_baseline_fields(tmp_path):
    source = _synthetic_source(tmp_path)
    output = source["results_root"] / "legacy_attempt"
    produced = run_v14_saved_candidate(source=source, output_dir=output)
    report_path = Path(produced["path"])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["scope"].pop("state_rows", None)
    for row in report["candidate_rhs"]:
        row.pop("baseline_mode", None)
        row.pop("baseline_z", None)
    report_path.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    digest = hashlib.sha256(report_path.read_bytes()).hexdigest()
    checked = check_v14_saved_candidate(
        source=source,
        candidate_report_path=report_path,
        candidate_report_sha256=digest,
        output_path=source["results_root"] / "legacy_attempt_check.json",
    )
    assert checked["check_completed"] is True
    assert checked["scope"]["stage"] == "initial_screen"
    assert checked["full_owner_unlocked"] is False


def test_v14_decimal_recheck_accepts_same_or_new_source_but_keeps_window_binding(
    tmp_path, monkeypatch
):
    class CandidateReplayReached(Exception):
        pass

    def run_case(
        name: str,
        *,
        consumer_source_sha: str,
        review_source_sha: str,
        same_window: bool,
    ) -> None:
        case_root = tmp_path / name
        results_root = case_root / "results"
        results_root.mkdir(parents=True)
        fixed_window_path = case_root / "fixed-window.json"
        fixed_window_bytes = b"fixed approved window"
        fixed_window_path.write_bytes(fixed_window_bytes)
        fixed_window_sha = hashlib.sha256(fixed_window_bytes).hexdigest()
        review_window_path = fixed_window_path
        review_window_sha = fixed_window_sha
        if not same_window:
            review_window_path = case_root / "different-window.json"
            review_window_bytes = b"different approved window"
            review_window_path.write_bytes(review_window_bytes)
            review_window_sha = hashlib.sha256(review_window_bytes).hexdigest()

        consumer_contract = {
            "kind": "consumer",
            "source": {"sha": consumer_source_sha},
            "window": {"path": str(fixed_window_path), "sha256": fixed_window_sha},
        }
        consumer_contract_path = case_root / "consumer-contract.json"
        consumer_contract_path.write_text(
            json.dumps(consumer_contract, sort_keys=True), encoding="utf-8"
        )
        consumer_contract_sha = hashlib.sha256(
            consumer_contract_path.read_bytes()
        ).hexdigest()

        review_contract = {
            "kind": "review",
            "execution_scope": TASK41_B0_V14_SAVED_RHS_CANDIDATE_SCOPE,
            "source": {"sha": review_source_sha},
            "window": {
                "path": str(review_window_path),
                "sha256": review_window_sha,
            },
        }
        review_contract_path = case_root / (
            f"execution_contract_source_{review_source_sha}_v14_same_lu_rhs_candidate_6h.json"
        )
        review_contract_path.write_text(
            json.dumps(review_contract, sort_keys=True), encoding="utf-8"
        )
        review_contract_sha = hashlib.sha256(
            review_contract_path.read_bytes()
        ).hexdigest()

        candidate_path = results_root / "candidate.json"
        prior_path = results_root / "prior-check.json"
        candidate = {
            "schema": checker_module.V14_CANDIDATE_REPORT_SCHEMA,
            "status": "CANDIDATE_PRODUCED_PENDING_INDEPENDENT_CHECK",
            "official_result": False,
            "scientific_qualified": False,
            "consumer_contract_path": str(consumer_contract_path),
            "consumer_contract_sha256": consumer_contract_sha,
            "consumer_window_sha256": fixed_window_sha,
            "getrs_count": 12,
            "scope": {
                "stage": "initial_screen",
                "cells": list(V14_CELLS),
                "columns": list(V14_COLUMNS),
                "full_owner": False,
            },
            "candidate_rhs": [
                {"cell_index": cell, "column": column}
                for cell in V14_CELLS
                for column in V14_COLUMNS
            ],
        }
        candidate_path.write_text(
            json.dumps(candidate, sort_keys=True), encoding="utf-8"
        )
        candidate_sha = hashlib.sha256(candidate_path.read_bytes()).hexdigest()
        prior = {
            "schema": checker_module.V14_CANDIDATE_CHECK_SCHEMA,
            "status": "INCONCLUSIVE",
            "check_completed": True,
            "candidate_passed": None,
            "official_result": False,
            "scientific_qualified": False,
            "candidate_report_path": str(candidate_path),
            "candidate_report_sha256": candidate_sha,
            "consumer_contract_sha256": consumer_contract_sha,
            "consumer_window_sha256": fixed_window_sha,
        }
        prior_path.write_text(json.dumps(prior, sort_keys=True), encoding="utf-8")
        prior_sha = hashlib.sha256(prior_path.read_bytes()).hexdigest()

        calls = {}

        def require_contract(
            path,
            *,
            expected_sha256,
            current_root,
            check_current_source,
            require_clean_source,
            case_id,
        ):
            calls["contract"] = {
                "path": Path(path).resolve(),
                "expected_sha256": expected_sha256,
                "check_current_source": check_current_source,
                "require_clean_source": require_clean_source,
                "case_id": case_id,
            }
            assert calls["contract"]["path"] == review_contract_path.resolve()
            assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected_sha256
            return review_contract, review_contract_sha

        def load_window(contract, *, current_root, require_current_boot):
            if contract["kind"] == "consumer":
                return SimpleNamespace(
                    path=fixed_window_path, sha256=fixed_window_sha
                )
            return SimpleNamespace(
                path=review_window_path, sha256=review_window_sha
            )

        def stop_at_saved_array_replay(**kwargs):
            raise CandidateReplayReached

        with monkeypatch.context() as patch:
            patch.setattr(
                checker_module, "require_task41_p0_contract", require_contract
            )
            patch.setattr(
                checker_module, "load_task41_p0_fixed_window", load_window
            )
            patch.setattr(
                checker_module, "check_v14_saved_candidate",
                stop_at_saved_array_replay,
            )
            kwargs = {
                "repo_root": case_root,
                "source": {
                    "results_root": results_root,
                    "consumer_contract": consumer_contract,
                    "consumer_contract_path": str(consumer_contract_path),
                    "consumer_contract_sha256": consumer_contract_sha,
                    "consumer_window_sha256": fixed_window_sha,
                },
                "candidate_report_path": candidate_path,
                "candidate_report_sha256": candidate_sha,
                "prior_independent_check_path": prior_path,
                "prior_independent_check_sha256": prior_sha,
                "review_contract_path": review_contract_path,
                "review_contract_sha256": review_contract_sha,
                "output_path": results_root / "decimal-output.json",
            }
            if same_window:
                with pytest.raises(CandidateReplayReached):
                    checker_module.check_v14_saved_candidate_decimal_residuals(
                        **kwargs
                    )
            else:
                with pytest.raises(ValueError, match="same fixed window"):
                    checker_module.check_v14_saved_candidate_decimal_residuals(
                        **kwargs
                    )

        assert calls["contract"]["check_current_source"] is True
        assert calls["contract"]["require_clean_source"] is True
        assert calls["contract"]["case_id"] == "B0"

    same_sha = "a" * 40
    current_sha = "b" * 40
    run_case(
        "same-source",
        consumer_source_sha=same_sha,
        review_source_sha=same_sha,
        same_window=True,
    )
    run_case(
        "new-source",
        consumer_source_sha=same_sha,
        review_source_sha=current_sha,
        same_window=True,
    )
    run_case(
        "window-drift",
        consumer_source_sha=same_sha,
        review_source_sha=same_sha,
        same_window=False,
    )
