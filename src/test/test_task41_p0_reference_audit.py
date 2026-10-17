"""Small production-format fixture for Task41 A2 reference-audit closeout."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from scipy import sparse


def _save_npy(path: Path, value: np.ndarray) -> dict[str, object]:
    with path.open("wb") as stream:
        np.save(stream, value, allow_pickle=False)
    return {
        "path": str(path.resolve()),
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def test_task41_weak_mode_delta_uses_global_incident_scale(tmp_path: Path) -> None:
    from src.runners.task41_p0_comparison import compare_task41_modal_artifacts

    keys = {
        "side": np.asarray(["top", "top"]),
        "m": np.asarray([0, 1], dtype=np.int64),
        "n": np.asarray([0, 0], dtype=np.int64),
        "polarization": np.asarray(["s", "s"]),
        "physical_boundary_outgoing_representable": np.asarray([True, True]),
        "physical_boundary_incident_amplitude": np.asarray([1.0 + 0.0j, 0.0j]),
        "physical_boundary_amplitude_coordinate": np.asarray("physical_boundary_trace"),
    }
    reference_modal = tmp_path / "reference_modal.npz"
    candidate_modal = tmp_path / "candidate_modal.npz"
    for path, outgoing in (
        (reference_modal, np.asarray([1.0 + 0.0j, 0.0j])),
        (candidate_modal, np.asarray([1.0 + 0.0j, 2.5e-2 + 0.0j])),
    ):
        np.savez(
            path,
            **keys,
            physical_boundary_outgoing_amplitude=outgoing,
        )

    orders = [
        {
            "side": "top", "m": 0, "n": 0, "polarization": "s",
            "R": 1.0, "T": 0.0, "power_ratio": 1.0,
        },
        {
            "side": "top", "m": 1, "n": 0, "polarization": "s",
            "R": 0.0, "T": 0.0, "power_ratio": 1.0e-10,
        },
    ]
    reference_orders = tmp_path / "reference_orders.json"
    candidate_orders = tmp_path / "candidate_orders.json"
    for path in (reference_orders, candidate_orders):
        path.write_text(json.dumps({"orders": orders}) + "\n", encoding="utf-8")

    result = compare_task41_modal_artifacts(
        reference_modal, candidate_modal, reference_orders, candidate_orders
    )
    assert result["significant_mode_count"] == 1
    weak = result["weak_channel_incident_scaled_deltas"]
    assert len(weak) == 1
    assert weak[0]["mode_key"] == ["top", 1, 0, "s"]
    assert weak[0]["incident_scale"] == pytest.approx(1.0)
    assert weak[0]["incident_scaled_absolute_delta"] == pytest.approx(2.5e-2)


def test_task41_metric_packet_rejects_incomplete_independent_rows(tmp_path: Path) -> None:
    from src.runners.task41_p0_comparison import evaluate_task41_metric_packet

    packet_path = tmp_path / "metric_packet.json"
    arrays_path = tmp_path / "metric_packet.npz"
    binding_sha = "a" * 64
    reference = np.asarray([1.0, 2.0, 3.0, 4.0], dtype=np.complex128)
    candidate = reference.copy()
    candidate[2] += 1.0e-6
    independent = np.asarray([0, 2, 3], dtype=np.int64)
    difference = candidate[independent] - reference[independent]
    archive = {
        "independent_indices": independent,
        "a1_mpc_slave_local_rows": np.asarray([1], dtype=np.int64),
        "a2_mpc_slave_local_rows": np.asarray([1], dtype=np.int64),
        "mass_reference_applied": reference[independent].copy(),
        "mass_difference_applied": difference.copy(),
        "scaled_curl_reference_applied": reference[independent].copy(),
        "scaled_curl_difference_applied": difference.copy(),
    }

    def write_packet(values: dict[str, np.ndarray], metrics: dict[str, float]) -> None:
        np.savez(arrays_path, **values)
        records = {
            name: {
                "array_key": name,
                "shape": list(value.shape),
                "dtype": str(value.dtype),
            }
            for name, value in values.items()
        }
        records["schema"] = "task41.p0.a1_a2_metric_packet.v1"
        records["a1_binding_sha256"] = binding_sha
        records["arrays"] = {
            "path": str(arrays_path.resolve()),
            "sha256": hashlib.sha256(arrays_path.read_bytes()).hexdigest(),
        }
        records["metrics"] = metrics
        packet_path.write_text(
            json.dumps(records, sort_keys=True) + "\n", encoding="utf-8"
        )

    reference_norm_sq = float(np.vdot(reference[independent], reference[independent]).real)
    difference_norm_sq = float(np.vdot(difference, difference).real)
    relative = float(np.sqrt(difference_norm_sq / reference_norm_sq))
    metrics = {
        "electric_relative_l2": relative,
        "scaled_curl_relative_l2": relative,
    }
    write_packet(archive, metrics)

    result = evaluate_task41_metric_packet(
        packet_path,
        reference_full_field=reference,
        candidate_full_field=candidate,
        expected_binding_sha256=binding_sha,
    )
    assert result["raw_action_algebra_recomputed"] is True
    assert result["electric_relative_l2"] == pytest.approx(relative)

    incomplete = {
        **archive,
        "independent_indices": np.asarray([0, 2], dtype=np.int64),
        "mass_reference_applied": reference[[0, 2]].copy(),
        "mass_difference_applied": difference[[0, 1]].copy(),
        "scaled_curl_reference_applied": reference[[0, 2]].copy(),
        "scaled_curl_difference_applied": difference[[0, 1]].copy(),
    }
    write_packet(incomplete, metrics)
    with pytest.raises(ValueError, match="does not cover every independent full-space row"):
        evaluate_task41_metric_packet(
            packet_path,
            reference_full_field=reference,
            candidate_full_field=candidate,
            expected_binding_sha256=binding_sha,
        )


def test_task41_a2_reference_checker_reapplies_real_ten_q_packets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.runners.task41_p0_checker import _task41_a2_reference_audit_checks
    from src.runners.task41_p0_contract import _prepare_task41_a2_q_csr_reuse
    from src.solvers.task40_v30_qualified_q_csr import QualifiedQCSRProvider
    from src.solvers import task40_v10_p6_periodic_profile as periodic_profiles
    from src.solvers.task40_v10_p6_mumps import (
        AllQExactMumps,
        task41_a2_all_q_factor_contract,
    )
    from src.solvers.task40_v10_p6_periodic_profile import TASK41_G13_A2_P6_PROFILE
    from src.solvers.task40_v30_selected_q_csr import (
        finalize_selected_q_csr,
        qualify_selected_q_native,
        selected_q_csr_actions,
        selected_q_operator_identity,
    )

    profile = replace(
        TASK41_G13_A2_P6_PROFILE,
        global_cell_axes=(1, 10, 1),
        rows_per_q=3,
        trace_rows_per_q=2,
        local_width_per_q=3,
        q_port_counts=(1,) * 10,
        sector_port_counts=(2,) * 5,
    )
    monkeypatch.setattr(periodic_profiles, "TASK41_G13_A2_P6_PROFILE", profile)
    artifact_root = tmp_path
    numerical_output = artifact_root / "numerical_output"
    numerical_output.mkdir()
    q_maps = {
        q: sparse.eye(3, dtype=np.complex128, format="csr") for q in range(10)
    }
    matrices: dict[int, sparse.csr_matrix] = {}
    csr_artifacts_by_q: dict[int, dict[str, dict[str, object]]] = {}
    selector_entries: dict[int, dict[str, object]] = {}
    qualifications: dict[int, dict[str, object]] = {}
    source_sha = "1" * 40
    window_sha = "2" * 64
    execution_identity = {"source_sha": source_sha, "window_sha256": window_sha}
    modes = (SimpleNamespace(side="top", m=0, n=0, polarization="s"),)
    original_h = np.asarray([1.0 + 0.1j, 1.2 + 0.2j, 0.8 + 0.3j])

    for q in range(10):
        dense = np.asarray(
            [
                [3.0 + q, 0.2j, 0.0],
                [0.2j, 4.0 + q, 0.1],
                [0.0, 0.1, 5.0 + q],
            ],
            dtype=np.complex128,
        )
        source_matrix = sparse.csr_matrix(dense)
        csr_artifacts = {}
        for name in ("data", "indices", "indptr"):
            row = _save_npy(tmp_path / f"q{q}_{name}.npy", getattr(source_matrix, name))
            csr_artifacts[name] = row
        matrix = sparse.csr_matrix(
            tuple(
                np.load(csr_artifacts[name]["path"], mmap_mode="r+", allow_pickle=False)
                for name in ("data", "indices", "indptr")
            ),
            shape=source_matrix.shape,
            copy=False,
        )
        matrices[q] = matrix

    for q in range(10):
        matrix = matrices[q]
        source_matrix = sparse.csr_matrix(matrix.toarray())
        csr_artifacts = {
            name: _save_npy(tmp_path / f"q{q}_{name}.npy", getattr(source_matrix, name))
            for name in ("data", "indices", "indptr")
        }
        # Reopen through the same disk-backed CSR shape that the production
        # finalizer requires; the numerical matrix remains identical.
        matrix = sparse.csr_matrix(
            tuple(
                np.load(csr_artifacts[name]["path"], mmap_mode="r+", allow_pickle=False)
                for name in ("data", "indices", "indptr")
            ),
            shape=source_matrix.shape,
            copy=False,
        )
        matrices[q] = matrix
        pattern_record = {"csr_artifacts": csr_artifacts}
        inputs = {
            "case1_full": np.asarray([1.0 + 0.1j, 2.0 - 0.2j, 3.0 + 0.3j]),
            "case1_trace_only": np.asarray([1.0 + 0.1j, 2.0 - 0.2j, 0.0j]),
            "case1_port_only": np.asarray([0.0j, 0.0j, 3.0 + 0.3j]),
            "case2_full": np.asarray([0.5 + 0.4j, 1.1 - 0.3j, 2.0 + 0.7j]),
        }
        csr_outputs = selected_q_csr_actions(
            matrix,
            inputs,
            allocation_gate=lambda _name, _facts: {},
            q_index=q,
        )
        native_outputs = {name: value.copy() for name, value in csr_outputs.items()}
        native_components = {
            "volume": native_outputs["case1_full"].copy(),
            "minus_D": np.zeros(3, dtype=np.complex128),
            "C": np.zeros(3, dtype=np.complex128),
            "Hhat": np.zeros(3, dtype=np.complex128),
        }
        peer_q = q + 5 if q < 5 else q - 5
        peer_input = np.asarray([1.0 + 0.2j, 0.8 + 0.1j, 1.2 + 0.3j])
        peer_diagonal = np.asarray(matrices[peer_q] @ peer_input, dtype=np.complex128)
        zero_cross = np.zeros(3, dtype=np.complex128)
        leakage = {
            "q_to_peer": {"input_q": q, "output_q": peer_q, "relative": 0.0},
            "peer_to_q": {
                "input_q": peer_q,
                "output_q": q,
                "relative": 0.0,
                "peer_csr_native_relative": 0.0,
            },
        }
        native_result = {
            **qualify_selected_q_native(
                matrix=matrix,
                inputs=inputs,
                csr_outputs=csr_outputs,
                native_outputs=native_outputs,
                native_components_case1=native_components,
                paired_leakage=leakage,
                trace_rows=2,
            ),
            "inputs": inputs,
            "csr_outputs": csr_outputs,
            "native_outputs": native_outputs,
            "native_components_case1": native_components,
            "paired_peer_input": peer_input,
            "paired_peer_native_diagonal": peer_diagonal,
            "paired_peer_native_cross": zero_cross,
            "paired_selected_native_cross": zero_cross,
            "paired_peer_case2_cross": zero_cross,
            "native_input_seeds": {"case1_full": 1, "case2_full": 2},
        }
        operator_identity = selected_q_operator_identity(
            scientific_input_sha256="a" * 64,
            profile_identity=profile.identity(),
            ordered_modes=modes,
            q_map=q_maps[q],
            original_h=original_h,
        )
        manifest, qualification, selector = finalize_selected_q_csr(
            matrix=matrix,
            pattern_record=pattern_record,
            numeric_facts={"numeric_fill_complete": True},
            native_result=native_result,
            output_directory=tmp_path,
            profile=profile.name,
            q_index=q,
            twist_index=q % 5,
            q_map=q_maps[q],
            original_h=original_h,
            profile_identity=profile.identity(),
            ordered_modes=modes,
            scientific_input_sha256="a" * 64,
            operator_identity=operator_identity,
            matrix_source_identity=execution_identity,
            execution_identity=execution_identity,
            producer_identity={"kind": "task41_checker_fixture"},
        )
        assert manifest["status"] == "COMPLETE_CSR"
        assert qualification["status"] == "PASS"
        selector_entries[q] = selector
        qualifications[q] = qualification

    with AllQExactMumps(
        matrices,
        allocation_gate=lambda _name, _facts: {},
        expected_shapes=(3,) * 10,
        profile=profile,
        full_storage_rows=6,
        task41_a2_config=task41_a2_all_q_factor_contract(),
        output_directory=tmp_path,
    ) as factors:
        factor_audit = factors.audit.copy()
        factor_audit["factor_tests"] = [dict(row) for row in factors.audit["factor_tests"]]
        factor_audit["second_rhs_tests"] = [dict(row) for row in factors.audit["second_rhs_tests"]]
        factor_audit["factor_inputs"] = [dict(row) for row in factors.audit["factor_inputs"]]

    sector_audits = []
    for twist in range(5):
        pair = [twist, twist + 5]
        receipts = []
        facts_by_q = {}
        for q in pair:
            selector = selector_entries[q]
            qualification = qualifications[q]
            manifest_ref = selector["csr_manifest"]
            qualification_ref = selector["native_qualification"]
            receipts.append(
                {
                    "q_index": q,
                    "twist_index": twist,
                    "manifest_status": "COMPLETE_CSR",
                    "qualification_status": "PASS",
                    "csr_manifest_path": manifest_ref["path"],
                    "csr_manifest_sha256": manifest_ref["sha256"],
                    "native_qualification_path": qualification_ref["path"],
                    "native_qualification_sha256": qualification_ref["sha256"],
                    "maximum_relative_error": qualification["maximum_relative_error"],
                }
            )
            facts_by_q[str(q)] = {
                "status": "PASS",
                "four_complete_csr_actions_passed": True,
                "paired_sector_leakage_passed": True,
                "csr_manifest_sha256": manifest_ref["sha256"],
                "native_qualification_sha256": qualification_ref["sha256"],
            }
        sector_audits.append(
            {
                "global_q_indices": pair,
                "task41_a2_independent_q_csr_preparation": {
                    "selected_q_indices": pair,
                    "all_complete_native_pass": True,
                    "four_complete_csr_actions_passed": True,
                    "paired_sector_leakage_passed": True,
                    "qualification_identity": {
                        "q_indices": pair,
                        "twist_index": twist,
                        "profile_identity": profile.identity(),
                    },
                    "selector_entries": [selector_entries[q] for q in pair],
                    "qualification_receipts": receipts,
                    "native_facts_by_q": facts_by_q,
                },
            }
        )
    consumer_execution = {"source_sha": "7" * 40, "window_sha256": "8" * 64}
    reuse_binding = _prepare_task41_a2_q_csr_reuse(
        tmp_path,
        [
            Path(selector_entries[q]["csr_manifest"]["path"])
            for q in (0, 5)
        ],
        source_sha=consumer_execution["source_sha"],
        window_sha256=consumer_execution["window_sha256"],
        expected_input_sha256="a" * 64,
    )
    provider = QualifiedQCSRProvider(
        tmp_path / reuse_binding["selector_path"],
        selector_sha256=reuse_binding["selector_sha256"],
        repo_root=tmp_path,
        path_resolver=lambda path: Path(path).resolve(),
        allocation_gate=lambda *_args, **_kwargs: None,
        consumer_receipt_directory=tmp_path / "consumer_receipts",
        consumer_import_authorizations=reuse_binding["consumer_import_authorizations"],
    )
    imported_receipts = [
        provider.load(
            q,
            0,
            expected_operator_identity=selector_entries[q]["operator_identity"],
            expected_execution_identity=consumer_execution,
            expected_q_map=q_maps[q],
            expected_original_h=original_h,
        )[1]
        for q in (0, 5)
    ]
    imported_preparation = sector_audits[0]["task41_a2_independent_q_csr_preparation"]
    imported_preparation.update(
        {
            "schema": "task41.p0.a2_saved_q_csr_import_audit.v1",
            "qualification_origin": "saved_v30_native_pass_cross_window_import",
            "imported_saved_q_indices": [0, 5],
            "selector_entries": [
                dict(provider.entries[q]) for q in (0, 5)
            ],
            "qualification_receipts": imported_receipts,
        }
    )
    imported_preparation.pop("native_facts_by_q")

    snapshot = {
        "factor_audit_before_destroy": factor_audit,
        "q_matrix_audits_before_destroy": {
            str(q): {"shape": list(matrix.shape), "nnz": matrix.nnz}
            for q, matrix in matrices.items()
        },
        "sector_audits_before_destroy": sector_audits,
    }

    result = _task41_a2_reference_audit_checks(
        {
            "reference_audit_snapshot": snapshot,
            "campaign_authority": {
                "source_sha": consumer_execution["source_sha"],
                "campaign_window_sha256": consumer_execution["window_sha256"],
                "q_csr_reuse": reuse_binding,
            },
        },
        numerical_output,
        repo_root=tmp_path,
    )
    assert result["all_q_factor_probes_reapplied"] is True
    assert result["factor_probe_count"] == 10
    assert result["all_q_four_action_csr_reapplied"] is True
    assert result["q_csr_action_count"] == 40
    assert result["sector_count"] == 5
    assert result["saved_native_qualification_q_indices"] == [0, 5]
    assert result["fresh_native_qualification_q_indices"] == [1, 2, 3, 4, 6, 7, 8, 9]
