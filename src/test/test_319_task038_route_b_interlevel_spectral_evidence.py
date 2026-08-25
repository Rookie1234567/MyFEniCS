"""Pure Route-B profile contracts for the shared interlevel checker."""

from __future__ import annotations

import copy
import hashlib
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import benchmarks.run_task038_full3d_interlevel_spectral as worker
import benchmarks.task038_full3d_interlevel_spectral_checker as checker
from src.solvers.fullspace_lor_interlevel_route_selection import PROBE_NAMES
from src.test.test_316_task038_interlevel_spectral_evidence import (
    _synthetic_record as _route_a_record,
    _topology_facts,
    _write_json,
)


EXPECTED_SHA = "b" * 40


def _refresh_closeout(record_path: Path, marker_dir: Path) -> None:
    closeout_path = marker_dir / "record_closeout.json"
    if closeout_path.is_file():
        closeout = json.loads(closeout_path.read_text(encoding="utf-8"))
    else:
        closeout = {
            "schema": checker.ROUTE_B_MARKER_SCHEMA,
            "marker": "record_closeout",
            "source_sha": EXPECTED_SHA,
            "wall_time_ns": 2000,
            "facts": {"record_path": str(record_path.resolve())},
        }
    closeout["facts"]["record_sha256"] = hashlib.sha256(record_path.read_bytes()).hexdigest()
    _write_json(closeout_path, closeout)


def _local_transfer_facts(pair: tuple[int, int], matrix: np.ndarray) -> dict[str, object]:
    node_shape = (343, 27) if pair == (6, 2) else (27, 8)
    node = np.ones(node_shape, dtype=np.complex128)
    audit = {
        "fine_degree": pair[0], "coarse_degree": pair[1],
        "edge_shape": tuple(matrix.shape), "node_shape": node_shape,
        "edge_dtype": "complex128", "node_dtype": "complex128",
        "edge_numeric_bytes": int(matrix.nbytes), "node_numeric_bytes": int(node.nbytes),
        "edge_nnz": int(np.count_nonzero(matrix)), "node_nnz": int(np.count_nonzero(node)),
        "coarse_transform_condition": 1.0,
        "edge_line_integral_relative": 0.0, "curl_flux_relative": 0.0,
        "gradient_commuting_relative": 0.0, "node_transfer_relative": 0.0,
        "adjoint_work_relative": 0.0, "linearity_relative": 0.0,
        "repeat_relative": 0.0, "input_unchanged": True, "finite": True,
        "global_transfer_matrix": False,
        "schema": "task038.local_interlevel_edge_transfer.v1",
        "line_integral_histopolation": True, "simple_injection": False,
        "structural_projection": True, "structural_forbidden_nnz_after": 0,
        "oracle_workspace_retained": False,
        "nested_tiled_geometric": pair == (6, 2),
        "generic_high_polynomial_reconstruction": False,
        "shared_consistency": True, "p62_p21_composition_relative": 0.0,
    }
    if pair == (6, 2):
        subset = [float(value).hex() for value in (0.0, 0.5, 1.0)]
        audit.update({
            "gll_subset_exact": True,
            "coarse_gll_subset_indices": [0, 3, 6],
            "coarse_gll_subset_coordinate_identity": subset,
            "fine_gll_subset_coordinate_identity": list(subset),
        })
    fake_transfer = SimpleNamespace(
        fine_degree=pair[0], coarse_degree=pair[1],
        edge_transfer=matrix, node_transfer=node, audit=audit,
    )
    return worker._compact_local_transfer(fake_transfer)


def _level_facts(rows: int) -> dict[str, object]:
    parent = _topology_facts()
    raw = _topology_facts()
    return {
        "matrix": {"rows": rows, "cols": rows},
        "parent_global_unique_rows": 100,
        "raw_global_unique_rows": 100,
        "parent_topology": parent,
        "raw_topology": raw,
    }


def _make_route_b_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    record_path, compact_path, record = _route_a_record(tmp_path)
    raw_dir = Path(record["raw_dir"])
    marker_dir = raw_dir / "markers"
    for path in marker_dir.glob("*.json"):
        path.unlink()
    p62 = np.vstack((np.eye(54, dtype=np.complex128), np.zeros((828, 54), dtype=np.complex128)))
    p21 = np.vstack((np.eye(12, dtype=np.complex128), np.zeros((42, 12), dtype=np.complex128)))
    arrays: dict[str, np.ndarray] = {"p62": p62, "p21": p21}
    class_audits: list[dict[str, object]] = []
    inventory = record["material_inventory"]
    for item in inventory["classes"]:
        digest = item["class_digest"]
        prefix = f"class_{digest}"
        b2 = np.eye(54, dtype=np.complex128)
        b6p = p62.copy()
        e_min = np.eye(54, dtype=np.complex128)[:, 0]
        e_max = np.eye(54, dtype=np.complex128)[:, -1]
        arrays.update({
            f"{prefix}__b2": b2,
            f"{prefix}__b6p": b6p,
            f"{prefix}__eigenvector_min": e_min,
            f"{prefix}__eigenvector_max": e_max,
        })
        class_audits.append({
            "class_digest": digest,
            "class_identity": copy.deepcopy(item["class_identity"]),
            "class_digest_matches_inventory": True,
            "tag": item["tag"], "material_role": item["material_role"],
            "cell_count_local": 1, "cell_count_global": 1,
            "method": "lor_edge_geometric_mg_6_2_1_nested_v1",
            "rank": 54, "rank_threshold": 1.0e-12,
            "sigma_min": 1.0, "sigma_max": 1.0,
            "hermitian_defect_b2": 0.0, "hermitian_defect_g62": 0.0,
            "minimum_eigenvalue_b2": 1.0, "minimum_eigenvalue_g62": 1.0,
            "strict_spd_b2": True, "strict_spd_g62": True,
            "lambda_min": 1.0, "lambda_max": 1.0,
            "spectral_condition": 1.0,
            "endpoint_residual_min": 0.0, "endpoint_residual_max": 0.0,
            "nested_energy_relative": 0.0, "finite": True,
            "p62_shape": [882, 54], "p62_nnz": 54,
            "b2_shape": [54, 54], "b6p_shape": [882, 54],
            "nested_tiled_geometric": True,
            "generic_high_polynomial_reconstruction": False,
            "b6_dense_retained": False, "g62_dense_retained": False,
            "gate_passed": True, "gate_failures": [],
        })
    probes: list[dict[str, object]] = []
    global_p62 = np.vstack((np.eye(7, dtype=np.complex128), np.zeros((4, 7), dtype=np.complex128)))
    for index, name in enumerate(PROBE_NAMES):
        x = np.arange(7, dtype=np.float64) + 1.0 + index + 1j * (index + 0.5)
        x2 = np.arange(7, dtype=np.float64) + 2.0 + index - 1j * (index + 0.25)
        projected = global_p62 @ x
        projected2 = global_p62 @ x2
        combo = checker.ALPHA * projected + checker.BETA * projected2
        fine_dual = np.arange(11, dtype=np.float64) + 0.5 + 1j * (index + 0.75)
        adjoint = global_p62.conj().T @ fine_dual
        roles = worker._probe_array_roles(name, coarse_action_role="B2")
        values = {
            "source_before": x, "source_after": x.copy(), "source2": x2,
            "projected": projected, "projected_repeat": projected.copy(),
            "projected2": projected2, "projected_combo": combo,
            "fine_dual": fine_dual, "adjoint": adjoint,
            "b2": x.copy(), "b6p": projected.copy(),
        }
        arrays.update({roles[key]: value for key, value in values.items()})
        energy = complex(np.vdot(x, x))
        probes.append({
            "schema": checker.ROUTE_B_PROBE_SCHEMA, "name": name,
            "q": 1.0, "q_imag_defect": 0.0,
            "energy_coarse": [energy.real, energy.imag],
            "energy_fine": [energy.real, energy.imag], "energy_imag_defect": 0.0,
            "source_norm": float(np.linalg.norm(x)), "source_finite": True,
            "source_nonzero": True, "adjoint_work_relative": 0.0,
            "linearity_relative": 0.0, "repeat_relative": 0.0,
            "finite": True, "input_unchanged": True, "phase_once": True,
            "source_generation": checker.ROUTE_B_SOURCE_GENERATION[name],
            "source_before_digest": checker._digest(x),
            "source_after_digest": checker._digest(x), "raw_roles": roles,
            "coarse_action_role": "B2",
        })
    global_p21 = np.vstack((np.eye(5, dtype=np.complex128), np.zeros((2, 5), dtype=np.complex128)))
    owner_source = np.arange(5, dtype=np.float64) + 1.0 + 0.5j
    owner_source2 = np.arange(5, dtype=np.float64) + 2.0 - 0.25j
    owner_projected = global_p21 @ owner_source
    owner_projected2 = global_p21 @ owner_source2
    owner_combo = checker.ALPHA * owner_projected + checker.BETA * owner_projected2
    owner_dual = np.arange(7, dtype=np.float64) + 0.75 + 0.25j
    owner_adjoint = global_p21.conj().T @ owner_dual
    owner_roles = worker._owner_probe_array_roles()
    owner_values = {
        "source_before": owner_source, "source_after": owner_source.copy(),
        "source2": owner_source2, "projected": owner_projected,
        "projected_repeat": owner_projected.copy(), "projected2": owner_projected2,
        "projected_combo": owner_combo, "fine_dual": owner_dual,
        "adjoint": owner_adjoint,
    }
    arrays.update({owner_roles[key]: value for key, value in owner_values.items()})
    owner_probe = {
        "schema": checker.ROUTE_B_PROBE_SCHEMA,
        "name": "owner_packet_deterministic", "pair": [2, 1],
        "source_generation": "deterministic_owner_packet_p21",
        "source_norm": float(np.linalg.norm(owner_source)),
        "source_finite": True, "source_nonzero": True,
        "adjoint_work_relative": 0.0, "linearity_relative": 0.0,
        "repeat_relative": 0.0, "finite": True, "input_unchanged": True,
        "phase_once": True, "source_before_digest": checker._digest(owner_source),
        "source_after_digest": checker._digest(owner_source), "raw_roles": owner_roles,
    }
    raw_descriptor = worker._write_raw_arrays(raw_dir, arrays, filename="route_b_arrays.npz")
    manifest_path = Path(record["provenance"]["r3_long_tail_manifest_path"])
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    monkeypatch.setattr(checker, "R3_LONG_TAIL_MANIFEST_SHA256", manifest_sha)
    record["source"] = {
        "start": {"commit_sha": EXPECTED_SHA, "branch": worker.BRANCH, "clean": True},
        "end": {"commit_sha": EXPECTED_SHA, "branch": worker.BRANCH, "clean": True},
    }
    command = [
        record["runtime"]["sys_executable"], "-m", worker.MODULE, "--stage", "r3", "--case", "p6-h10-mpi1",
        "--raw-dir", str(raw_dir.resolve()), "--record", str(record_path.resolve()),
        "--expected-source-sha", EXPECTED_SHA, "--expected-mpi-size", "1",
        "--input", str((Path(__file__).resolve().parents[2] / "input/templates/full3d_iterative_example.dat").resolve()),
        "--r3-long-tail-manifest", str(manifest_path.resolve()), "--route", "b",
    ]
    record.update({
        "route": "B", "candidate": checker.ROUTE_B_CANDIDATE,
        "schema": checker.ROUTE_B_SCHEMA, "stage": "r3",
        "command": command, "material_classes": class_audits,
        "local_gate_passed": True, "not_run_by_local_gate": [],
        "raw_arrays": raw_descriptor,
        "provenance": {
            "r3_long_tail_manifest_path": str(manifest_path.resolve()),
            "r3_long_tail_manifest_sha256": manifest_sha,
            "r3_long_tail_expected_sha256": checker.R3_LONG_TAIL_MANIFEST_SHA256,
            "r3_long_tail_source_sha": checker.R3_LONG_TAIL_SOURCE_SHA,
            "p62_constructed_once": True, "p62_construction_count": 1,
            "p62_construction_source": "build_local_interlevel_edge_transfer(6,2)",
            "p21_construction_count": 1,
            "p21_construction_source": "build_local_interlevel_edge_transfer(2,1)",
        },
        "settings": {
            "probe_names": list(PROBE_NAMES), "probe_alpha": [0.37, 0.19],
            "probe_beta": [-0.23, 0.41],
            "source_canonicalization": "owner_roundtrip_reduced_primal",
            "rank": 54, "levels": [6, 2, 1], "transfer_pair": [6, 2],
            "lambda_min_limit": 0.50, "lambda_max_limit": 2.0,
            "condition_limit": 4.0, "nested_energy_limit": 1.0e-9,
            "hermitian_limit": 1.0e-12, "endpoint_residual_limit": 1.0e-10,
            "adjoint_limit": 1.0e-11, "linearity_limit": 1.0e-12,
            "repeat_limit": 1.0e-13, "probe_q_center": 1.0,
            "probe_q_abs_limit": 1.0e-9,
            "phase_once": "once_in_canonical_owner_route",
        },
        "architecture": {
            "case": record["architecture"]["case"],
            "extension": {
                key: value for key, value in record["architecture"]["extension"].items()
                if key != "p1_built"
            } | {
                "level1_raw_matrix_built": True,
                "p6_exact_factor": False,
                "hx_hierarchy_built": False,
                "pcgamg_hierarchy_built": False,
                "retains_per_apply_history": False,
            },
            "forbidden": record["architecture"]["forbidden"],
            "levels": {"level6": _level_facts(11), "level2": _level_facts(7), "level1": _level_facts(5)},
            "global_high_order_aij": False, "global_transfer_matrix": False,
            "numeric_allgather": False, "smoother_built": False,
            "ksp_created": False, "physical_solve": False, "recovery": False,
            "level1_raw_matrix_built": True,
            "level1_global_direct_factor": False, "p1_global_direct_factor": False,
        },
        "local_transfers": {
            "6_2": _local_transfer_facts((6, 2), p62),
            "2_1": _local_transfer_facts((2, 1), p21),
        },
            "p62_audit": worker._transfer_matrix_facts(p62), "p21_audit": worker._transfer_matrix_facts(p21),
        "probes": probes, "owner_probe": owner_probe,
    })
    record["architecture"]["forbidden"].update({
        "extension.p6_exact_factor": False,
        "extension.hx_hierarchy_built": False,
        "extension.pcgamg_hierarchy_built": False,
        "extension.retains_per_apply_history": False,
    })
    record["markers"] = {
        "relative_dir": "markers", "names": list(checker.ROUTE_B_PASS_MARKERS),
        "wall_time_ns": {},
    }
    for index, name in enumerate(checker.ROUTE_B_PASS_MARKERS):
        timestamp = 1000 + index
        _write_json(marker_dir / f"{name}.json", {
            "schema": checker.ROUTE_B_MARKER_SCHEMA, "marker": name,
            "source_sha": EXPECTED_SHA, "wall_time_ns": timestamp, "facts": {},
        })
        record["markers"]["wall_time_ns"][name] = timestamp
    _write_json(record_path, record)
    _write_json(marker_dir / "record_closeout.json", {
        "schema": checker.ROUTE_B_MARKER_SCHEMA, "marker": "record_closeout",
        "source_sha": EXPECTED_SHA, "wall_time_ns": 2000,
        "facts": {"record_path": str(record_path.resolve()), "record_sha256": hashlib.sha256(record_path.read_bytes()).hexdigest()},
    })
    watchdog_raw = compact_path.parent / "watchdog.raw.jsonl"
    watchdog_raw.write_text(json.dumps({"authority": {"process_tree": {"rss_bytes": 100, "swap_bytes": 0, "all_status_readable": True}}}) + "\n", encoding="utf-8")
    _write_json(compact_path, {
        "schema": checker.WATCHDOG_SCHEMA, "source_sha": EXPECTED_SHA,
        "worker_command": command, "worker_record": str(record_path.resolve()),
        "worker_raw_dir": str(raw_dir.resolve()), "watchdog_raw": str(watchdog_raw.resolve()),
        "raw_sha256": hashlib.sha256(watchdog_raw.read_bytes()).hexdigest(),
        "sample_count": 1, "peak_process_tree_rss_bytes": 100,
        "max_process_tree_swap_bytes": 0, "all_status_readable": True,
        "watchdog_poll_seconds": 0.25, "watchdog_rss_limit_bytes": 2_000_000_000,
        "returncode": 0, "natural_exit": True, "no_orphan": True,
        "stop_reason": "natural_exit",
    })
    return record_path, compact_path, record


def test_route_b_synthetic_pass_and_authorities(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    record_path, compact_path, _record = _make_route_b_record(tmp_path, monkeypatch)
    result = checker.check_record(record_path, compact_path, EXPECTED_SHA)
    assert result["classification"] == "STRUCTURALLY_QUALIFIED"
    assert result["contract_errors"] == []
    assert result["gate_failures"] == []
    assert result["metrics"]["owner_probe"]["adjoint_work_relative"] == 0.0


@pytest.mark.parametrize("mutation", ("missing_b2", "energy", "owner", "classification", "resource"))
def test_route_b_representative_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str) -> None:
    record_path, compact_path, record = _make_route_b_record(tmp_path, monkeypatch)
    marker_dir = Path(record["raw_dir"]) / "markers"
    if mutation == "missing_b2":
        first = record["material_classes"][0]["class_digest"]
        with np.load(Path(record["raw_dir"]) / "route_b_arrays.npz", allow_pickle=False) as loaded:
            values = {key: loaded[key] for key in loaded.files if not key.endswith(f"{first}__b2")}
        np.savez_compressed(Path(record["raw_dir"]) / "route_b_arrays.npz", **values)
        record["raw_arrays"]["sha256"] = hashlib.sha256((Path(record["raw_dir"]) / "route_b_arrays.npz").read_bytes()).hexdigest()
        record["raw_arrays"]["arrays"].pop(f"class_{first}__b2")
    elif mutation == "energy":
        first = record["material_classes"][0]["class_digest"]
        raw_path = Path(record["raw_dir"]) / "route_b_arrays.npz"
        key = f"class_{first}__b6p"
        with np.load(raw_path, allow_pickle=False) as loaded:
            values = {name: loaded[name].copy() for name in loaded.files}
        values[key] *= 1.0 + 1.0e-6
        np.savez_compressed(raw_path, **values)
        record["raw_arrays"]["sha256"] = hashlib.sha256(raw_path.read_bytes()).hexdigest()
        record["raw_arrays"]["arrays"][key]["sha256"] = worker._array_descriptor(values[key])["sha256"]
        p62 = values["p62"]
        b2 = values[f"class_{first}__b2"]
        g62 = p62.conj().T @ values[key]
        eigenvalues = np.linalg.eigvalsh(g62)
        class_item = record["material_classes"][0]
        class_item.update({
            "hermitian_defect_g62": checker._hermitian_defect(g62),
            "minimum_eigenvalue_g62": float(eigenvalues[0]),
            "lambda_min": float(eigenvalues[0]),
            "lambda_max": float(eigenvalues[-1]),
            "spectral_condition": float(eigenvalues[-1] / eigenvalues[0]),
            "endpoint_residual_min": checker._endpoint_residual(
                g62, b2, float(eigenvalues[0]), values[f"class_{first}__eigenvector_min"],
            ),
            "endpoint_residual_max": checker._endpoint_residual(
                g62, b2, float(eigenvalues[-1]), values[f"class_{first}__eigenvector_max"],
            ),
            "nested_energy_relative": float(
                np.linalg.norm(g62 - b2) / np.linalg.norm(b2)
            ),
            "gate_passed": False,
            "gate_failures": ["nested energy"],
        })
        record["local_gate_passed"] = False
        record["not_run_by_local_gate"] = ["level2", "global_probes", "owner_probe"]
        record["probes"] = []
        record["owner_probe"] = None
        record["architecture"]["levels"]["level6"].update(
            {"foundation_built": True, "not_run_by_local_gate": False}
        )
        record["architecture"]["levels"]["level2"] = {
            "foundation_built": False, "not_run_by_local_gate": True,
        }
        record["architecture"]["levels"]["level1"] = {
            "foundation_built": False, "not_run_by_local_gate": True,
        }
        record["architecture"]["level1_raw_matrix_built"] = False
        values = {
            name: value for name, value in values.items()
            if not name.startswith(("probe__", "owner21__"))
        }
        record["raw_arrays"] = worker._write_raw_arrays(
            Path(record["raw_dir"]), values, filename="route_b_arrays.npz"
        )
        for path in marker_dir.glob("*.json"):
            path.unlink()
        record["markers"] = {
            "relative_dir": "markers", "names": list(checker.ROUTE_B_FAIL_MARKERS),
            "wall_time_ns": {},
        }
        for index, name in enumerate(checker.ROUTE_B_FAIL_MARKERS):
            timestamp = 1000 + index
            _write_json(marker_dir / f"{name}.json", {
                "schema": checker.ROUTE_B_MARKER_SCHEMA, "marker": name,
                "source_sha": EXPECTED_SHA, "wall_time_ns": timestamp, "facts": {},
            })
            record["markers"]["wall_time_ns"][name] = timestamp
    elif mutation == "owner":
        roles = record["owner_probe"]["raw_roles"]
        source_role = roles["source_before"]
        source_after_role = roles["source_after"]
        raw_path = Path(record["raw_dir"]) / "route_b_arrays.npz"
        with np.load(raw_path, allow_pickle=False) as loaded:
            values = {name: loaded[name].copy() for name in loaded.files}
        values[source_role][:] = 0.0
        values[source_after_role][:] = 0.0
        np.savez_compressed(raw_path, **values)
        record["raw_arrays"]["sha256"] = hashlib.sha256(raw_path.read_bytes()).hexdigest()
        record["raw_arrays"]["arrays"][source_role]["sha256"] = worker._array_descriptor(values[source_role])["sha256"]
        record["raw_arrays"]["arrays"][source_after_role]["sha256"] = worker._array_descriptor(values[source_after_role])["sha256"]
        record["owner_probe"]["source_before_digest"] = checker._digest(values[source_role])
        record["owner_probe"]["source_after_digest"] = checker._digest(values[source_after_role])
        record["owner_probe"]["source_norm"] = 0.0
        record["owner_probe"]["source_nonzero"] = False
        record["owner_probe"]["adjoint_work_relative"] = 1.0
    elif mutation == "classification":
        record["classification"] = "POSITIVE_AUXILIARY_PASS"
    else:
        watchdog = json.loads(compact_path.read_text(encoding="utf-8"))
        watchdog_raw = Path(watchdog["watchdog_raw"])
        raw_row = json.loads(watchdog_raw.read_text(encoding="utf-8").splitlines()[0])
        raw_row["authority"]["process_tree"]["swap_bytes"] = 1
        watchdog_raw.write_text(json.dumps(raw_row, separators=(",", ":")) + "\n", encoding="utf-8")
        watchdog["raw_sha256"] = hashlib.sha256(watchdog_raw.read_bytes()).hexdigest()
        watchdog["max_process_tree_swap_bytes"] = 1
        _write_json(compact_path, watchdog)
    _write_json(record_path, record)
    _refresh_closeout(record_path, marker_dir)
    result = checker.check_record(record_path, compact_path, EXPECTED_SHA)
    assert result["passed"] is False
    assert result["classification"] != "POSITIVE_AUXILIARY_PASS"
    if mutation == "energy":
        assert any("nested energy" in failure for failure in result["gate_failures"])
        assert result["classification"] == "CLOSED_BY_INTERLEVEL_SPECTRAL_GATE"
    elif mutation == "owner":
        assert result["classification"] == "CLOSED_BY_INTERLEVEL_SPECTRAL_GATE"
        assert any("source finite/nonzero" in failure for failure in result["gate_failures"])
    elif mutation in {"missing_b2", "classification"}:
        assert result["classification"] == "CONTRACT_INVALID"
    else:
        assert result["classification"] == "RESOURCE_GATE_FAILED"


def test_route_b_wrong_b2_role_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    record_path, compact_path, record = _make_route_b_record(tmp_path, monkeypatch)
    probe = record["probes"][0]
    probe["raw_roles"]["b3"] = probe["raw_roles"].pop("b2")
    _write_json(record_path, record)
    _refresh_closeout(record_path, Path(record["raw_dir"]) / "markers")
    result = checker.check_record(record_path, compact_path, EXPECTED_SHA)
    assert result["classification"] == "CONTRACT_INVALID"
    assert any("raw roles" in error or "missing" in error for error in result["contract_errors"])


def test_route_b_compact_helper_uses_real_transfer_audit() -> None:
    matrix = np.eye(54, dtype=np.complex128)
    compact = _local_transfer_facts((6, 2), matrix)
    assert "local_map" in compact and "local_transfer" in compact
    assert compact["pair"] == [6, 2]
    assert compact["local_map"]["edge_rows"] == 54
    assert compact["local_transfer"]["edge_nnz"] == 54
    assert "import numpy as np" in inspect.getsource(worker.run_worker)


def test_route_b_stage_contract_is_explicit() -> None:
    source = Path(worker.__file__).read_text(encoding="utf-8")
    assert "choices=(STAGE, ROUTE_B_STAGE)" in source
    assert "Route-A uses --stage r1 and Route-B uses --stage r3" in source


def test_route_b_cli_passes_r3_profile_without_worker_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(worker, "run_worker", lambda *args: calls.append(args))
    args = [
        "--stage", "r3", "--case", "p6-h10-mpi1",
        "--raw-dir", str(tmp_path / "raw"), "--record", str(tmp_path / "record.json"),
        "--expected-source-sha", EXPECTED_SHA, "--expected-mpi-size", "1",
        "--input", str(tmp_path / "input.dat"),
        "--r3-long-tail-manifest", str(tmp_path / "manifest.json"), "--route", "b",
    ]
    assert worker.main(args) == 0
    assert calls and calls[0][-1] == "b"
    with pytest.raises(SystemExit):
        worker.main([*args[:1], "r1", *args[2:]])
