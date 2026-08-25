"""Pure evidence-contract tests for the V12 Route-A R1 layer."""

from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

import benchmarks.run_task038_full3d_interlevel_spectral as worker
import benchmarks.task038_full3d_interlevel_spectral_checker as checker
from src.solvers.fullspace_lor_interlevel_spectral_dolfinx import (
    PROBE_NAMES,
    build_material_class_inventory_from_rows,
    source_generation_identity,
)


REPO = Path(__file__).resolve().parents[2]
EXPECTED_SHA = "a" * 40
PYTHON = "/home/shenjh/Projects/MyFEniCS-Surrogate/.venv/bin/python"
INPUT_PATH = (REPO / "input/templates/full3d_iterative_example.dat").resolve()
SYNTHETIC_R3_BYTES = b'{"synthetic_r3_manifest":true}\n'
SYNTHETIC_R3_SHA = hashlib.sha256(SYNTHETIC_R3_BYTES).hexdigest()


@pytest.fixture(autouse=True)
def _synthetic_r3_manifest(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(checker, "R3_LONG_TAIL_MANIFEST_SHA256", SYNTHETIC_R3_SHA)


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _topology_facts() -> dict[str, object]:
    return {
        "owner_local_maps": True,
        "numeric_allgather": False,
        "global_transfer_matrix": False,
        "phase_application": "once_in_canonical_owner_route",
        "edge_orientation": "dolfinx_cell_permutation_Tt_then_T",
        "cell_permutation": "Tt_before_high_to_lor_and_T_after_lor_to_high",
        "floquet_phase": "complete_slave_edge_mapped_to_master_once",
        "slave_master_complete": True,
        "local_unique_edge_count": 100,
        "owned_unique_edge_count": 100,
        "global_unique_edge_count": 100,
    }


def _synthetic_architecture() -> dict[str, object]:
    case_names = (
        "global_high_order_aij", "global_dense_transfer", "global_numeric_allgather",
        "numeric_allgather", "scalar_node_matrix_built", "global_direct_coarse_built",
        "recovery_field_arrays_built", "p6_exact_edge_factor_built", "hx_hierarchy_built",
        "pcgamg_hierarchy_built", "physical_solve", "recovery", "global_transfer_matrix",
    )
    extension_names = (
        "global_high_order_aij", "global_transfer_matrix", "numeric_allgather",
        "p1_global_direct_factor", "p1_built", "smoother_built", "ksp_created",
        "physical_solve", "recovery",
    )
    case = {name: False for name in case_names}
    extension = {name: False for name in extension_names}
    forbidden = {
        name: False for name in (
            "global_high_order_aij", "global_transfer_matrix", "numeric_allgather",
            "p1_global_direct_factor", "p1_built", "smoother_built", "ksp_created",
            "physical_solve", "recovery",
        )
    }
    levels = {}
    for name in ("level6", "level3"):
        parent = _topology_facts()
        raw = _topology_facts()
        levels[name] = {
            "parent_global_unique_rows": 100,
            "raw_global_unique_rows": 100,
            "matrix": {
                "rows": 7 if name == "level3" else 11,
                "cols": 7 if name == "level3" else 11,
            },
            "parent_topology": parent,
            "raw_topology": raw,
        }
    return {
        "case": case,
        "extension": extension,
        "forbidden": forbidden,
        "levels": levels,
        "global_high_order_aij": False,
        "global_transfer_matrix": False,
        "numeric_allgather": False,
        "p1_built": False,
        "level1_built": False,
        "smoother_built": False,
        "ksp_created": False,
        "physical_solve": False,
        "recovery": False,
    }


def _synthetic_record(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    raw_dir = tmp_path / "raw"
    marker_dir = raw_dir / "markers"
    raw_dir.mkdir()
    marker_dir.mkdir()
    record_path = tmp_path / "record.json"
    watchdog_raw = tmp_path / "watchdog.raw.jsonl"
    watchdog_compact = tmp_path / "watchdog.json"
    r3_manifest = tmp_path / "r3-manifest.json"
    r3_manifest.write_bytes(SYNTHETIC_R3_BYTES)
    p63 = np.vstack((np.eye(144, dtype=np.complex128), np.zeros((738, 144), dtype=np.complex128)))
    rows = [
        {"tag": 1, "material_role": "air", "widths": (1.0, 1.0, 1.0), "curl_coefficient": 1.0, "mass_coefficient": 1.0},
        {"tag": 2, "material_role": "substrate", "widths": (1.0, 1.0, 1.0), "curl_coefficient": 1.0, "mass_coefficient": 1.0},
        {"tag": 3, "material_role": "grating", "widths": (1.0, 1.0, 1.0), "curl_coefficient": 1.0, "mass_coefficient": 1.0},
    ]
    inventory = build_material_class_inventory_from_rows(rows)
    inventory["classes"] = sorted(inventory["classes"], key=lambda item: item["class_digest"])
    for item in inventory["classes"]:
        item["cell_count_global"] = 1
    inventory["cell_count_local"] = 3
    inventory["cell_count_global"] = 3
    b3 = np.eye(144, dtype=np.complex128)
    b6p = p63.copy()
    arrays: dict[str, np.ndarray] = {"p63": p63}
    class_audits: list[dict[str, object]] = []
    for class_item in inventory["classes"]:
        digest = class_item["class_digest"]
        arrays.update({
            f"class_{digest}__b3": b3.copy(),
            f"class_{digest}__b6p": b6p.copy(),
            f"class_{digest}__eigenvector_min": np.eye(144, dtype=np.complex128)[:, 0],
            f"class_{digest}__eigenvector_max": np.eye(144, dtype=np.complex128)[:, -1],
        })
        class_audits.append({
            "class_digest": digest,
            "class_identity": class_item["class_identity"],
            "class_digest_matches_inventory": True,
            "tag": class_item["tag"],
            "material_role": class_item["material_role"],
            "cell_count_local": 1,
            "cell_count_global": 1,
            "rank": 144,
            "sigma_min": 1.0,
            "sigma_max": 1.0,
            "hermitian_defect_b3": 0.0,
            "hermitian_defect_g63": 0.0,
            "minimum_eigenvalue_b3": 1.0,
            "minimum_eigenvalue_g63": 1.0,
            "lambda_min": 1.0,
            "lambda_max": 1.0,
            "spectral_condition": 1.0,
            "endpoint_residual_min": 0.0,
            "endpoint_residual_max": 0.0,
            "finite": True,
            "gate_passed": True,
            "gate_failures": [],
        })
    probes: list[dict[str, object]] = []
    probe_transfer = np.vstack((np.eye(7, dtype=np.complex128), np.zeros((4, 7), dtype=np.complex128)))
    for index, name in enumerate(PROBE_NAMES):
        x = (np.arange(7, dtype=np.float64) + 1.0 + index) + 1j * (index + 0.5)
        x2 = (np.arange(7, dtype=np.float64) + 2.0 + index) - 1j * (index + 0.25)
        projected = probe_transfer @ x
        projected2 = probe_transfer @ x2
        combo = checker.ALPHA * projected + checker.BETA * projected2
        fine_dual = (np.arange(11, dtype=np.float64) + 0.5) + 1j * (index + 0.75)
        adjoint = probe_transfer.conj().T @ fine_dual
        roles = worker._probe_array_roles(name)
        values = {
            "source_before": x, "source_after": x.copy(), "source2": x2,
            "projected": projected, "projected_repeat": projected.copy(),
            "projected2": projected2, "projected_combo": combo,
            "fine_dual": fine_dual, "adjoint": adjoint, "b3": x.copy(), "b6p": projected.copy(),
        }
        arrays.update({roles[key]: value for key, value in values.items()})
        energy = complex(np.vdot(x, x))
        probes.append({
            "schema": "task038.full3d.route-a.global-probe.v1",
            "name": name, "q": 1.0, "q_imag_defect": 0.0,
            "energy_coarse": [energy.real, energy.imag],
            "energy_fine": [energy.real, energy.imag], "energy_imag_defect": 0.0,
            "source_norm": float(np.linalg.norm(x)), "source_finite": True, "source_nonzero": True,
            "adjoint_work_relative": 0.0, "linearity_relative": 0.0,
            "repeat_relative": 0.0, "finite": True, "input_unchanged": True,
            "phase_once": True, "source_generation": checker.SOURCE_GENERATION[name],
            "source_before_digest": checker._digest(x), "source_after_digest": checker._digest(x),
            "raw_roles": roles,
        })
    raw_descriptor = worker._write_raw_arrays(raw_dir, arrays)
    command = [
        PYTHON, "-m", worker.MODULE, "--stage", "r1", "--case", "p6-h10-mpi1",
        "--raw-dir", str(raw_dir.resolve()), "--record", str(record_path.resolve()),
        "--expected-source-sha", EXPECTED_SHA, "--expected-mpi-size", "1",
        "--input", str(INPUT_PATH), "--r3-long-tail-manifest", str(r3_manifest.resolve()),
    ]
    runtime = {
        "qualified_activation": "1", "mpi_size": 1, "scalar_dtype": "complex128",
        "int_dtype": "int32", "sys_executable": PYTHON,
        "threads": {"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"},
    }
    source = {"commit_sha": EXPECTED_SHA, "branch": worker.BRANCH, "clean": True}
    r3_sha = hashlib.sha256(r3_manifest.read_bytes()).hexdigest()
    record: dict[str, object] = {
        "schema": "task038.full3d.interlevel-spectral.r1-record.v1", "stage": "r1",
        "case": "p6-h10-mpi1", "degree": 6, "h_nm": 10.0, "wavelength_nm": 13.5, "mpi_size": 1,
        "branch": worker.BRANCH, "raw_dir": str(raw_dir.resolve()), "record_path": str(record_path.resolve()),
        "command": command, "source": {"start": source, "end": source}, "runtime": runtime,
        "input_identity": {
            "path_relative": "input/templates/full3d_iterative_example.dat",
            "raw_bytes": checker.EXPECTED_INPUT_BYTES, "raw_sha256": checker.EXPECTED_INPUT_SHA256,
            "resolved_bytes": checker.EXPECTED_RESOLVED_BYTES, "resolved_sha256": checker.EXPECTED_RESOLVED_SHA256,
            "physical_model_sha256": checker.EXPECTED_PHYSICAL_MODEL_SHA256,
        },
        "provenance": {
            "r3_long_tail_manifest_path": str(r3_manifest.resolve()), "r3_long_tail_manifest_sha256": r3_sha,
            "r3_long_tail_expected_sha256": checker.R3_LONG_TAIL_MANIFEST_SHA256,
            "r3_long_tail_source_sha": checker.R3_LONG_TAIL_SOURCE_SHA,
            "p63_constructed_once": True, "p63_construction_count": 1,
            "p63_construction_source": "build_local_interlevel_edge_transfer(6,3)",
        },
        "settings": {
            "probe_names": list(PROBE_NAMES), "probe_alpha": [0.37, 0.19], "probe_beta": [-0.23, 0.41],
            "source_canonicalization": "owner_roundtrip_reduced_primal", "rank": 144,
            "levels": [6, 3], "transfer_pair": [6, 3], "lambda_min_limit": 0.10,
            "lambda_max_limit": 10.0, "condition_limit": 100.0, "hermitian_limit": 1.0e-12,
            "endpoint_residual_limit": 1.0e-10, "adjoint_limit": 1.0e-12,
            "linearity_limit": 1.0e-12, "repeat_limit": 1.0e-13,
            "probe_q_interval": [0.10, 10.0], "phase_once": "once_in_canonical_owner_route",
        },
        "architecture": _synthetic_architecture(), "material_inventory": inventory,
        "material_classes": class_audits, "local_gate_passed": True,
        "not_run_by_local_gate": [], "raw_arrays": raw_descriptor, "p63_audit": {
            "shape": [882, 144], "dtype": "complex128", "sigma_min": 1.0, "sigma_max": 1.0,
            "rank_threshold": 882 * np.finfo(float).eps, "rank": 144, "finite": True,
        },
        "probes": probes,
        "markers": {"relative_dir": "markers", "names": list(checker.PASS_MARKERS), "wall_time_ns": {}},
        "record_authority": "raw-facts-only; checker derives classification",
    }
    for index, name in enumerate(checker.PASS_MARKERS):
        timestamp = 1000 + index
        _write_json(marker_dir / f"{name}.json", {"schema": checker.MARKER_SCHEMA, "marker": name, "source_sha": EXPECTED_SHA, "wall_time_ns": timestamp, "facts": {}})
        record["markers"]["wall_time_ns"][name] = timestamp
    _write_json(record_path, record)
    closeout = {
        "schema": checker.MARKER_SCHEMA, "marker": "record_closeout", "source_sha": EXPECTED_SHA, "wall_time_ns": 2000,
        "facts": {"record_path": str(record_path.resolve()), "record_sha256": hashlib.sha256(record_path.read_bytes()).hexdigest()},
    }
    _write_json(marker_dir / "record_closeout.json", closeout)
    raw_row = {"authority": {"process_tree": {"rss_bytes": 100, "swap_bytes": 0, "all_status_readable": True}}}
    watchdog_raw.write_text(json.dumps(raw_row, separators=(",", ":")) + "\n", encoding="utf-8")
    watchdog = {
        "schema": checker.WATCHDOG_SCHEMA, "source_sha": EXPECTED_SHA, "worker_command": command,
        "worker_record": str(record_path.resolve()), "worker_raw_dir": str(raw_dir.resolve()),
        "watchdog_raw": str(watchdog_raw.resolve()), "raw_sha256": hashlib.sha256(watchdog_raw.read_bytes()).hexdigest(),
        "sample_count": 1, "peak_process_tree_rss_bytes": 100, "max_process_tree_swap_bytes": 0,
        "all_status_readable": True, "watchdog_poll_seconds": 0.25, "watchdog_rss_limit_bytes": 2_000_000_000,
        "returncode": 0, "natural_exit": True, "no_orphan": True, "stop_reason": "natural_exit",
    }
    _write_json(watchdog_compact, watchdog)
    return record_path, watchdog_compact, record


def test_material_inventory_exact_identity_and_probe_order() -> None:
    rows = [
        {"tag": 1, "material_role": "air", "widths": (1.0, 1.0, 1.0), "curl_coefficient": 1.0, "mass_coefficient": 1.0},
        {"tag": 1, "material_role": "air", "widths": (1.0, 1.0, np.nextafter(1.0, 2.0)), "curl_coefficient": 1.0, "mass_coefficient": 1.0},
    ]
    inventory = build_material_class_inventory_from_rows(rows)
    assert inventory["class_count"] == 2
    assert inventory["exact_float64_identity"] is True
    assert {item["material_role"] for item in inventory["classes"]} == {"air"}
    assert [item["class_digest"] for item in inventory["classes"]] == sorted(item["class_digest"] for item in inventory["classes"])
    assert tuple(PROBE_NAMES) == tuple(checker.PROBE_NAMES)
    assert source_generation_identity("random") == checker.SOURCE_GENERATION["random"]


@pytest.mark.parametrize("mutation", ("missing_role", "swapped_role_tag"))
def test_material_role_coverage_and_identity_fail_closed(tmp_path: Path, mutation: str) -> None:
    record_path, compact_path, record = _synthetic_record(tmp_path)
    if mutation == "missing_role":
        record["material_inventory"]["classes"] = [
            item for item in record["material_inventory"]["classes"]
            if item["material_role"] != "grating"
        ]
        record["material_inventory"]["class_count"] = 2
        record["material_inventory"]["cell_count_local"] = 2
        record["material_inventory"]["cell_count_global"] = 2
        record["material_classes"] = [
            item for item in record["material_classes"]
            if item["material_role"] != "grating"
        ]
        _write_json(record_path, record)
        result = checker.check_record(record_path, compact_path, EXPECTED_SHA)
        assert result["passed"] is False
        assert any("role" in error for error in result["contract_errors"])
        return

    item = record["material_inventory"]["classes"][0]
    old_role = item["material_role"]
    swapped_role = {"air": "grating", "grating": "substrate", "substrate": "air"}[old_role]
    swapped_tag = item["tag"]
    identity = copy.deepcopy(item["class_identity"])
    identity["material_coefficient_identity"]["material_role"] = swapped_role
    identity["material_coefficient_identity"]["class_name"] = f"{swapped_role}_tag_{swapped_tag}"
    item.update({
        "material_role": swapped_role,
        "tag": swapped_tag,
        "class_identity": identity,
        "class_digest": checker._semantic_sha(identity),
    })
    audit = record["material_classes"][0]
    audit.update({
        "material_role": swapped_role,
        "tag": swapped_tag,
        "class_identity": copy.deepcopy(identity),
        "class_digest": item["class_digest"],
        "class_digest_matches_inventory": True,
    })
    assert checker._semantic_sha(item["class_identity"]) == item["class_digest"]
    errors: list[str] = []
    checker._check_material_inventory(record["material_inventory"], record["material_classes"], errors)
    assert any("role/tag mapping mismatch" in error for error in errors)
    assert not any("digest is not identity-bound" in error for error in errors)


def test_p63_is_reused_by_material_class(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.solvers.fullspace_lor_interlevel_spectral as core

    p63 = np.zeros((882, 144), dtype=np.complex128)
    calls = {"builder": 0, "audit": 0}

    def forbidden_builder(*_args, **_kwargs):
        calls["builder"] += 1
        raise AssertionError("P63 was rebuilt")

    def fake_matrix(degree, _nodes, _widths, **_kwargs):
        return np.eye(882 if degree == 6 else 144, dtype=np.complex128)

    def fake_audit(_p63, _b3, _b6p, *, class_identity):
        calls["audit"] += 1
        return core.RouteASpectralResult(
            core.MappingProxyType({"class_digest": class_identity["class_digest"]}),
            core.MappingProxyType({}),
        )

    monkeypatch.setattr(core, "build_local_interlevel_edge_transfer", forbidden_builder)
    monkeypatch.setattr(core, "_assemble_lor_matrix", fake_matrix)
    monkeypatch.setattr(core, "audit_route_a_spectrum", fake_audit)
    result = core.build_route_a_material_class(p63=p63)
    assert result.audit["class_digest"]
    assert calls == {"builder": 0, "audit": 1}


def test_synthetic_record_passes_independent_checker(tmp_path: Path) -> None:
    record_path, compact, _record = _synthetic_record(tmp_path)
    result = checker.check_record(record_path, compact, EXPECTED_SHA)
    assert result["passed"] is True
    assert result["contract_errors"] == []
    assert result["gate_failures"] == []


@pytest.mark.parametrize("mutation", ("q", "phase", "rank", "extra_raw", "missing_marker", "stored_pass"))
def test_synthetic_contract_and_gate_mutations_fail_closed(tmp_path: Path, mutation: str) -> None:
    record_path, compact, record = _synthetic_record(tmp_path)
    if mutation == "q":
        record["probes"][0]["q"] = 11.0
    elif mutation == "phase":
        record["probes"][0]["phase_once"] = False
    elif mutation == "rank":
        record["material_classes"][0]["rank"] = 143
    elif mutation == "extra_raw":
        raw_dir = Path(record["raw_dir"])
        with np.load(raw_dir / "route_a_arrays.npz", allow_pickle=False) as loaded:
            values = {name: loaded[name] for name in loaded.files}
        values["unexpected"] = np.zeros(1, dtype=np.complex128)
        np.savez_compressed(raw_dir / "route_a_arrays.npz", **values)
        record["raw_arrays"]["sha256"] = hashlib.sha256((raw_dir / "route_a_arrays.npz").read_bytes()).hexdigest()
        record["raw_arrays"]["arrays"]["unexpected"] = worker._array_descriptor(values["unexpected"])
    elif mutation == "missing_marker":
        (Path(record["raw_dir"]) / "markers" / "probes_complete.json").unlink()
    elif mutation == "stored_pass":
        record["passed"] = True
        record["classification"] = "STRUCTURALLY_QUALIFIED"
    _write_json(record_path, record)
    result = checker.check_record(record_path, compact, EXPECTED_SHA)
    assert result["passed"] is False
    assert result["classification"] != "STRUCTURALLY_QUALIFIED"


def test_npz_descriptor_and_fine_coarse_shape_fail_closed(tmp_path: Path) -> None:
    record_path, compact, record = _synthetic_record(tmp_path)
    projected = record["probes"][0]["raw_roles"]["projected"]
    record["raw_arrays"]["arrays"][projected]["shape"] = [144]
    _write_json(record_path, record)
    result = checker.check_record(record_path, compact, EXPECTED_SHA)
    assert result["passed"] is False
    assert any("descriptor" in error or "shape" in error for error in result["contract_errors"])


def test_probe_shape_must_match_level_matrix_authority(tmp_path: Path) -> None:
    record_path, compact, record = _synthetic_record(tmp_path)
    record["architecture"]["levels"]["level3"]["matrix"] = {"rows": 8, "cols": 8}
    _write_json(record_path, record)
    result = checker.check_record(record_path, compact, EXPECTED_SHA)
    assert result["passed"] is False
    assert any("probe shape closure failed" in error for error in result["contract_errors"])


def test_checker_uses_generalized_hermitian_endpoint(tmp_path: Path) -> None:
    record_path, compact, record = _synthetic_record(tmp_path)
    digest = record["material_classes"][0]["class_digest"]
    raw_dir = Path(record["raw_dir"])
    with np.load(raw_dir / "route_a_arrays.npz", allow_pickle=False) as loaded:
        values = {name: loaded[name] for name in loaded.files}
    b6p = values[f"class_{digest}__b6p"].copy()
    b6p[0, 1] = 0.5
    values[f"class_{digest}__b6p"] = b6p
    np.savez_compressed(raw_dir / "route_a_arrays.npz", **values)
    record["raw_arrays"]["sha256"] = hashlib.sha256((raw_dir / "route_a_arrays.npz").read_bytes()).hexdigest()
    record["raw_arrays"]["arrays"][f"class_{digest}__b6p"] = worker._array_descriptor(b6p)
    _write_json(record_path, record)
    result = checker.check_record(record_path, compact, EXPECTED_SHA)
    assert result["passed"] is False
    assert any("Hermitian" in failure or "stored field" in error for failure in result["gate_failures"] for error in result["contract_errors"]) or result["gate_failures"]


@pytest.mark.parametrize("mutation", ("rss", "swap", "orphan"))
def test_watchdog_resource_and_lifecycle_boundaries(tmp_path: Path, mutation: str) -> None:
    record_path, compact_path, _record = _synthetic_record(tmp_path)
    compact = checker._read_json(compact_path)
    raw_path = Path(compact["watchdog_raw"])
    sample = json.loads(raw_path.read_text(encoding="utf-8"))
    if mutation == "rss":
        sample["authority"]["process_tree"]["rss_bytes"] = 2_000_000_000
        compact["peak_process_tree_rss_bytes"] = 2_000_000_000
    elif mutation == "swap":
        sample["authority"]["process_tree"]["swap_bytes"] = 1
        compact["max_process_tree_swap_bytes"] = 1
    else:
        compact["no_orphan"] = False
    raw_path.write_text(json.dumps(sample, separators=(",", ":")) + "\n", encoding="utf-8")
    compact["raw_sha256"] = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    _write_json(compact_path, compact)
    result = checker.check_record(record_path, compact_path, EXPECTED_SHA)
    assert result["passed"] is False
    if mutation in {"rss", "swap"}:
        assert result["classification"] == "RESOURCE_GATE_FAILED"
    else:
        assert result["classification"] == "EXECUTION_LIFECYCLE_FAILED"


def test_local_gate_negative_uses_not_run_marker_path(tmp_path: Path) -> None:
    record_path, compact_path, record = _synthetic_record(tmp_path)
    raw_dir = Path(record["raw_dir"])
    digest = record["material_classes"][0]["class_digest"]
    with np.load(raw_dir / "route_a_arrays.npz", allow_pickle=False) as loaded:
        values = {name: loaded[name] for name in loaded.files}
    values[f"class_{digest}__b3"] = np.zeros((144, 144), dtype=np.complex128)
    values = {name: value for name, value in values.items() if not name.startswith("probe__")}
    np.savez_compressed(raw_dir / "route_a_arrays.npz", **values)
    record["raw_arrays"]["sha256"] = hashlib.sha256((raw_dir / "route_a_arrays.npz").read_bytes()).hexdigest()
    record["raw_arrays"]["arrays"] = {
        name: worker._array_descriptor(value) for name, value in values.items()
    }
    for name in ("level3_complete", "probes_complete"):
        (raw_dir / "markers" / f"{name}.json").unlink()
    fail_names = list(checker.FAIL_MARKERS)
    for index, name in enumerate(("local_gate_failed", "level3_not_run", "probes_not_run"), start=5):
        _write_json(raw_dir / "markers" / f"{name}.json", {"schema": checker.MARKER_SCHEMA, "marker": name, "source_sha": EXPECTED_SHA, "wall_time_ns": 1000 + index, "facts": {}})
    record["local_gate_passed"] = False
    record["not_run_by_local_gate"] = ["level3", "global_probes"]
    record["architecture"]["levels"] = {
        "level6": {"foundation_built": True, "not_run_by_local_gate": False},
        "level3": {"foundation_built": False, "not_run_by_local_gate": True},
    }
    record["probes"] = []
    record["markers"]["names"] = fail_names
    record["markers"]["wall_time_ns"] = {
        name: 1000 + index for index, name in enumerate(fail_names)
    }
    release_path = raw_dir / "markers" / "release.json"
    release_row = checker._read_json(release_path)
    release_row["wall_time_ns"] = record["markers"]["wall_time_ns"]["release"]
    _write_json(release_path, release_row)
    _write_json(record_path, record)
    closeout = raw_dir / "markers" / "record_closeout.json"
    closeout_data = checker._read_json(closeout)
    closeout_data["facts"]["record_sha256"] = hashlib.sha256(record_path.read_bytes()).hexdigest()
    _write_json(closeout, closeout_data)
    result = checker.check_record(record_path, compact_path, EXPECTED_SHA)
    assert result["passed"] is False
    assert result["classification"] == "CLOSED_BY_INTERLEVEL_SPECTRAL_GATE"


def test_runner_import_boundary_and_marker_contract() -> None:
    tree = ast.parse(Path(worker.__file__).read_text(encoding="utf-8"))
    imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
    names = {alias.name.split(".")[0] for node in imports for alias in node.names}
    assert not names.intersection({"mpi4py", "petsc4py", "dolfinx"})
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                assert node.func.id not in {"solve", "KSP", "gmres"}
            if isinstance(node.func, ast.Attribute):
                assert node.func.attr not in {"solve", "createKSP"}
    assert tuple(worker.PASS_MARKERS) == checker.PASS_MARKERS
    assert tuple(worker.FAIL_MARKERS) == checker.FAIL_MARKERS
    assert any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_prepare_paths" for node in ast.walk(tree))


def test_checker_import_boundary_is_independent() -> None:
    tree = ast.parse(Path(checker.__file__).read_text(encoding="utf-8"))
    imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
    names = {alias.name.split(".")[0] for node in imports for alias in node.names}
    assert not names.intersection({"benchmarks", "src", "mpi4py", "petsc4py", "dolfinx"})
