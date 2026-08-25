"""Focused contract tests for the S5 capacity worker and checker."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from benchmarks import run_task038_full3d_lor_hierarchy_capacity as runner
from benchmarks import task038_full3d_lor_hierarchy_capacity_checker as checker


ROOT = Path(__file__).resolve().parents[2]
SOURCE_SHA = "a" * 40


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(value, dtype=np.complex128).view(np.uint8)).hexdigest()


def _command(record: Path, raw: Path) -> list[str]:
    return [
        "/abs/qualified/python", "-m", checker.MODULE,
        "--stage", "s5", "--case", checker.CASE,
        "--raw-dir", str(raw.resolve()), "--record", str(record.resolve()),
        "--expected-source-sha", SOURCE_SHA, "--expected-mpi-size", "1",
        "--input", str((ROOT / checker.TEMPLATE_RELATIVE_PATH).resolve()),
    ]


def _probe_arrays() -> tuple[dict[str, np.ndarray], dict]:
    arrays: dict[str, np.ndarray] = {}
    actions = {}
    for degree in checker.LEVELS:
        x = np.array([1 + 1j, 2 - 1j], dtype=np.complex128)
        y = 2.0 * x
        arrays[f"a{degree}_input"] = x
        arrays[f"a{degree}_out1"] = y
        arrays[f"a{degree}_out2"] = y.copy()
        actions[str(degree)] = {
            "diff_norm": 0.0,
            "ref_norm": float(np.linalg.norm(y)),
            "finite": True,
            "input_before_digest": _digest(x),
            "input_after_digest": _digest(x),
            "input_unchanged": True,
        }
    transfers = {}
    for pair in checker.PAIRS:
        tag, name = f"{pair[0]}{pair[1]}", f"{pair[0]}-{pair[1]}"
        x = np.array([1 + 1j, 2 - 1j], dtype=np.complex128)
        x2 = np.array([0.5 - 1j, -1 + 0.25j], dtype=np.complex128)
        y = np.array([3 - 0.5j, -2 + 2j], dtype=np.complex128)
        px1, px2 = x.copy(), x2.copy()
        pcombo = checker.ALPHA * px1 + checker.BETA * px2
        phy = y.copy()
        ca, fa = x.copy(), px1.copy()
        arrays.update({
            f"t{tag}_x": x, f"t{tag}_x2": x2, f"t{tag}_y": y,
            f"t{tag}_px1": px1, f"t{tag}_px_repeat": px1.copy(), f"t{tag}_px2": px2,
            f"t{tag}_pcombo": pcombo, f"t{tag}_phy": phy,
            f"t{tag}_coarse_action": ca, f"t{tag}_fine_action": fa,
        })
        ec = np.vdot(x, ca)
        transfers[name] = {
            "repeat_relative": 0.0,
            "linearity_relative": 0.0,
            "adjoint_relative": 0.0,
            "energy_relative": 0.0,
            "coarse_primal_source": checker.COARSE_PRIMAL_SOURCE,
            "energy_coarse": [float(ec.real), float(ec.imag)],
            "energy_fine": [float(ec.real), float(ec.imag)],
            "energy_imag_defect": abs(float(ec.imag)),
            "finite": True,
            "input_unchanged": True,
            "x_before_digest": _digest(x), "x_after_digest": _digest(x),
            "y_before_digest": _digest(y), "y_after_digest": _digest(y),
        }
    smoothers = {}
    for degree in (6, 3):
        rhs = np.array([1 + 0j, 2 + 0j], dtype=np.complex128)
        out = np.array([0.5 + 0j, 1 + 0j], dtype=np.complex128)
        arrays[f"s{degree}_rhs"] = rhs
        arrays[f"s{degree}_out1"] = out
        arrays[f"s{degree}_out2"] = out.copy()
        smoothers[str(degree)] = {
            "repeat_relative": 0.0, "finite": True,
            "input_before_digest": _digest(rhs), "input_after_digest": _digest(rhs),
            "input_unchanged": True,
        }
    rebuild_x = np.array([2 + 0.5j, -1 + 2j], dtype=np.complex128)
    rebuild_y = 3.0 * rebuild_x
    arrays["rebuild_a6_input"] = rebuild_x
    arrays["rebuild_a6_out1"] = rebuild_y
    arrays["rebuild_a6_out2"] = rebuild_y.copy()
    rebuild = {"diff_norm": 0.0, "ref_norm": float(np.linalg.norm(rebuild_y)),
               "finite": True, "input_before_digest": _digest(rebuild_x),
               "input_after_digest": _digest(rebuild_x), "input_unchanged": True}
    return arrays, {"actions": actions, "transfers": transfers, "smoothers": smoothers,
                    "rebuild": {"actions": {"6": rebuild}}}


def _fingerprint_payload() -> dict:
    bundle = runner._semantic_tree({
        "owner_schedule": {"ids": np.array([0, 1], dtype=np.int32)},
        "pull_schedule": (np.array([1, 0], dtype=np.int32), {"phase": np.array([1.0], dtype=np.float64)}),
    })
    descriptor = runner._array_descriptor(np.array([[1.0 + 0.0j, 0.5j]], dtype=np.complex128))
    matrix = {"rows": 8, "cols": 8, "nnz": 16, "index_bytes": 72,
              "numeric_bytes": 256, "type": "aij"}
    parent_inventory = {"parent_local_owned_rows": 2, "parent_local_unique_rows": 2,
                        "parent_global_unique_rows": 2, "parent_cell_count_local": 1,
                        "owner_route": "typed_complex128_alltoallv", "parent_matrix_built": False}
    raw_inventory = {"raw_local_owned_rows": 2, "raw_local_unique_rows": 2,
                     "raw_global_unique_rows": 2}
    topology = {
        "owner_local_maps": True, "numeric_allgather": False, "global_transfer_matrix": False,
        "phase_application": "once_in_canonical_owner_route",
        "edge_orientation": "dolfinx_cell_permutation_Tt_then_T",
        "cell_permutation": "Tt_before_high_to_lor_and_T_after_lor_to_high",
        "floquet_phase": "complete_slave_edge_mapped_to_master_once",
        "slave_master_complete": True, "global_unique_edge_count": 2,
        "owned_unique_edge_count": 2, "local_unique_edge_count": 2,
    }
    level = {
        "degree": 6, "matrix": matrix, "parent_inventory": parent_inventory,
        "raw_inventory": raw_inventory, "parent_topology": topology, "raw_topology": topology,
        "parent_topology_arrays": bundle,
        "raw_topology_arrays": bundle, "raw_map_arrays": bundle,
        "raw_permutations": descriptor, "incidence_unique": descriptor,
    }
    levels = {str(degree): dict(level, degree=degree) for degree in checker.LEVELS}
    local_map = {"edge_rows": 8, "edge_cols": 2, "edge_exact_nnz": 8,
                 "edge_numeric_bytes": 128, "node_rows": 4, "node_cols": 2,
                 "node_exact_nnz": 4, "node_numeric_bytes": 64}
    legality = {"edge_line_integral_relative": 0.0, "curl_flux_relative": 0.0,
                "gradient_commuting_relative": 0.0, "node_transfer_relative": 0.0,
                "adjoint_work_relative": 0.0, "linearity_relative": 0.0,
                "repeat_relative": 0.0, "line_integral_histopolation": True,
                "simple_injection": False, "structural_projection": True,
                "structural_forbidden_entry_count": 12,
                "structural_forbidden_nnz_after": 0,
                "structural_removed_nonzero_count": 1,
                "structural_removed_max_abs": 0.25}
    transfers = {
        name: {"pair": list(pair), "local_map": dict(local_map),
               "edge_transfer": descriptor, "node_transfer": descriptor,
               "local_legality": legality}
        for name, pair in zip(("6-3", "3-1"), checker.PAIRS)
    }
    smoothers = {str(degree): {"degree": degree, "fixed_degree": 3,
                               "power_steps": 10, "pre_sweeps": 1, "post_sweeps": 1,
                               "lambda_power10": 2.0,
                               "lambda_hi": 2.2, "lambda_lo": 0.22}
                 for degree in (6, 3)}
    return {"levels": levels, "transfers": transfers, "smoothers": smoothers}


def _valid_case(tmp_path: Path):
    raw = tmp_path / "worker_raw"
    raw.mkdir()
    record_path = tmp_path / "record.json"
    compact_path = tmp_path / "watchdog.json"
    watchdog_raw = tmp_path / "watchdog.raw.jsonl"
    arrays, probe_facts = _probe_arrays()
    np.savez(raw / "probe_facts.npz", **arrays)
    payload = _fingerprint_payload()
    fingerprint = runner._semantic_sha256(payload)
    topology = {
        "owner_local_maps": True, "numeric_allgather": False, "global_transfer_matrix": False,
        "phase_application": "once_in_canonical_owner_route",
        "edge_orientation": "dolfinx_cell_permutation_Tt_then_T",
        "cell_permutation": "Tt_before_high_to_lor_and_T_after_lor_to_high",
        "floquet_phase": "complete_slave_edge_mapped_to_master_once",
        "slave_master_complete": True, "global_unique_edge_count": 2,
        "owned_unique_edge_count": 2, "local_unique_edge_count": 2,
    }
    levels = {
        str(d): {"degree": d, "parent_local_owned_rows": 2, "parent_local_unique_rows": 2,
                 "parent_global_unique_rows": 2, "raw_local_owned_rows": 2,
                 "raw_local_unique_rows": 2, "raw_global_unique_rows": 2,
                 "parent_cell_count_local": 1, "owner_route": "typed_complex128_alltoallv",
                 "parent_matrix_built": False,
                 "matrix": {"rows": 8, "cols": 8, "nnz": 16, "index_bytes": 72, "numeric_bytes": 256, "type": "aij"},
                 "parent_topology": dict(topology), "raw_topology": dict(topology),
                 "topology_inventory_closed": True}
        for d in checker.LEVELS
    }
    local_audit = {
        "edge_line_integral_relative": 0.0, "curl_flux_relative": 0.0,
        "node_transfer_relative": 0.0,
        "gradient_commuting_relative": 0.0, "adjoint_work_relative": 0.0,
        "linearity_relative": 0.0, "repeat_relative": 0.0,
        "finite": True, "input_unchanged": True,
        "line_integral_histopolation": True, "simple_injection": False,
        "structural_projection": True,
        "structural_forbidden_entry_count": 12,
        "structural_forbidden_nnz_after": 0,
        "structural_removed_nonzero_count": 1,
        "structural_removed_max_abs": 0.25,
    }
    edge_descriptor = runner._array_descriptor(np.array([[1.0 + 0.0j, 0.5j]], dtype=np.complex128))
    transfers = {
        name: {"pair": list(pair), "global_transfer_matrix": False, "numeric_allgather": False, "local_transfer": local_audit,
               "local_transfer_arrays": {"edge_transfer": edge_descriptor, "node_transfer": edge_descriptor}, "local_map": {
            "edge_rows": 8, "edge_cols": 2, "edge_exact_nnz": 8, "edge_numeric_bytes": 128,
            "node_rows": 4, "node_cols": 2, "node_exact_nnz": 4, "node_numeric_bytes": 64,
        }} for name, pair in zip(("6-3", "3-1"), checker.PAIRS)
    }
    smoothers = {
        str(d): {"degree": d, "fixed_degree": 3, "power_steps": 10, "pre_sweeps": 1, "post_sweeps": 1,
                 "lambda_power10": 2.0, "lambda_hi": 2.2, "lambda_lo": 0.22,
                 "power_matrix_mult_count": 20, "matrix_mult_count": 26}
        for d in (6, 3)
    }
    forbidden = {key: False for key in (
        "global_high_order_aij", "global_transfer_matrix", "global_dense_transfer",
        "numeric_allgather", "global_numeric_allgather", "p1_global_direct_factor",
        "p6_exact_factor", "p6_exact_edge_factor_built", "hx_hierarchy_built", "pcgamg_hierarchy_built",
        "scalar_node_matrix_built", "global_direct_coarse_built",
        "recovery_field_arrays_built", "hx_or_node_action_built",
        "production_local_spectral_built", "physical_solve", "recovery",
    )}
    forbidden_sources = {key: "case.audit" for key in forbidden}
    forbidden_sources.update({key: "extension.audit" for key in (
        "global_transfer_matrix", "numeric_allgather", "p1_global_direct_factor",
        "p6_exact_factor", "hx_hierarchy_built", "pcgamg_hierarchy_built",
        "physical_solve", "recovery")})
    forbidden_sources["global_high_order_aij"] = "extension.levels[*].audit"
    known = {"mesh_space_mpc_known_array_bytes": None, "matrix_bytes": 100, "extension_level3_bytes": 100}
    resource = {"process_tree": {"rss_bytes": 1000, "swap_bytes": 0, "all_status_readable": True}}
    marker_dir = raw / "markers"
    marker_dir.mkdir()
    for index, name in enumerate(checker.MARKERS, start=1):
        (marker_dir / f"{name}.json").write_text(json.dumps({
            "schema": "task038.full3d.lor-hierarchy-capacity.marker.v1",
            "marker": name, "source_sha": SOURCE_SHA, "wall_time_ns": index,
        }, allow_nan=False) + "\n", encoding="utf-8")
    samples = []
    for index in range(1, 11):
        samples.append({"wall_time_ns": index, "authority": {"process_tree": {
            "rss_bytes": 500 + index * 10, "swap_bytes": 0, "all_status_readable": True,
        }}})
    watchdog_raw.write_text("".join(json.dumps(row, allow_nan=False) + "\n" for row in samples), encoding="utf-8")
    command = _command(record_path, raw)
    compact = {
        "schema": checker.WATCHDOG_SCHEMA, "source_sha": SOURCE_SHA,
        "watchdog_poll_seconds": 0.25, "worker_command": command, "worker_raw_dir": str(raw.resolve()),
        "worker_record": str(record_path.resolve()), "watchdog_raw": str(watchdog_raw.resolve()),
        "returncode": 0, "natural_exit": True, "no_orphan": True,
        "stop_reason": "natural_exit", "sample_count": len(samples),
        "all_status_readable": True, "peak_process_tree_rss_bytes": 600,
        "max_process_tree_swap_bytes": 0, "watchdog_rss_limit_bytes": checker.COLD_LIMIT,
        "raw_sha256": _sha(watchdog_raw),
    }
    compact_path.write_text(json.dumps(compact, allow_nan=False) + "\n", encoding="utf-8")
    first_facts = {key: value for key, value in probe_facts.items() if key != "rebuild"}
    record = {
        "schema": checker.SCHEMA, "stage": "s5", "case": checker.CASE,
        "degree": 6, "h_nm": 10.0, "wavelength_nm": 13.5, "mpi_size": 1,
        "raw_dir": str(raw.resolve()), "record_path": str(record_path.resolve()),
        "command": command,
        "source": {side: {"expected_sha": SOURCE_SHA, "commit_sha": SOURCE_SHA,
                           "branch": checker.BRANCH, "clean": True} for side in ("start", "end")},
        "runtime": {"qualified_activation": "1", "mpi_size": 1,
                    "petsc_scalar_type": "<class 'numpy.complex128'>",
                    "petsc_int_type": "<class 'numpy.int32'>", "sys_executable": command[0]},
        "input_identity": {"path_absolute": str((ROOT / checker.TEMPLATE_RELATIVE_PATH).resolve()),
                           "path_relative": checker.TEMPLATE_RELATIVE_PATH,
                           "raw_bytes": checker.EXPECTED_INPUT_BYTES,
                           "raw_sha256": checker.EXPECTED_INPUT_SHA256,
                           "resolved_bytes": checker.EXPECTED_RESOLVED_BYTES,
                           "resolved_sha256": checker.EXPECTED_RESOLVED_SHA256,
                           "physical_model_sha256": checker.EXPECTED_PHYSICAL_MODEL_SHA256},
        "provenance": {"source_sha": SOURCE_SHA, "branch": checker.BRANCH,
                       "input_sha256": checker.EXPECTED_INPUT_SHA256,
                       "resolved_sha256": checker.EXPECTED_RESOLVED_SHA256,
                       "physical_model_sha256": checker.EXPECTED_PHYSICAL_MODEL_SHA256},
        "settings": {"levels": list(checker.LEVELS), "pairs": [list(p) for p in checker.PAIRS],
                     "chebyshev_degree": 3, "power_steps": 10, "pre_sweeps": 1,
                     "post_sweeps": 1, "retained_dwell_seconds": 2.0},
        "reserve": {"basis_count": 21, "auxiliary_vector_count": 4, "vector_count": 25,
                    "touched": True, "local_entries_per_vector": 2, "local_numeric_bytes": 800},
        "architecture": {"forbidden": forbidden, "forbidden_sources": forbidden_sources,
                          "levels": levels, "transfers": transfers,
                          "smoothers": smoothers, "p1_coarse_budget": {
                              "status": "derived_estimate_only", "solver_selected": False,
                              "direct_factor_built": False, "matrix_payload_bytes": 100,
                              "fixed_work_vector_count": 8, "fixed_work_vector_bytes": 256,
                              "petsc_overhead_bytes": 5, "estimated_total_bytes": 361}},
        "probes": {"first": first_facts, "rebuild": probe_facts["rebuild"]},
        "raw_artifacts": {"probe_npz": {"relative_path": "probe_facts.npz", "sha256": _sha(raw / "probe_facts.npz")}},
        "fingerprint": {"first": {"payload": payload, "sha256": fingerprint},
                         "rebuild": {"payload": payload, "sha256": fingerprint},
                         "exact_identity": True},
        "markers": {"relative_dir": "markers", "names": list(checker.MARKERS)},
        "retained_ready_wall_time_ns": 9,
        "retained": {"known_bytes": known, "known_total_bytes": 200,
                      "measured_process_tree_rss_bytes": 1000,
                      "unattributed_remainder_bytes": 800,
                      "level6_foundation_ledger_included_once": True,
                      "bounded_temporary_bytes": {"included_in_known_total": False},
                      "resource": resource},
    }
    record_path.write_text(json.dumps(record, allow_nan=False) + "\n", encoding="utf-8")
    return record_path, compact_path, watchdog_raw, record, compact


def test_valid_record_and_checker_pass(tmp_path):
    record, compact, _raw, _record_value, _compact_value = _valid_case(tmp_path)
    result = checker.check_record(record, compact, SOURCE_SHA)
    assert result["passed"], result
    assert result["classification"] == "P6_LOR_EDGE_HIERARCHY_RESOURCE_PASS_WITH_COARSE_SOLVER_OPEN"


@pytest.mark.parametrize("mutation", ("energy", "adjoint", "factor", "fingerprint", "marker", "structural"))
def test_representative_contract_mutations_fail_closed(tmp_path, mutation):
    record_path, compact, _raw, record, _compact_value = _valid_case(tmp_path)
    if mutation == "energy":
        record["probes"]["first"]["transfers"]["6-3"]["energy_coarse"] = [999.0, 0.0]
    elif mutation == "adjoint":
        record["probes"]["first"]["transfers"]["6-3"]["adjoint_relative"] = 0.25
    elif mutation == "factor":
        record["architecture"]["forbidden"]["p6_exact_factor"] = True
    elif mutation == "fingerprint":
        record["fingerprint"]["rebuild"]["sha256"] = "b" * 64
    elif mutation == "structural":
        for transfer in record["architecture"]["transfers"].values():
            transfer["local_transfer"]["structural_forbidden_nnz_after"] = 1
        for name in ("first", "rebuild"):
            payload = record["fingerprint"][name]["payload"]
            for transfer in payload["transfers"].values():
                transfer["local_legality"]["structural_forbidden_nnz_after"] = 1
            record["fingerprint"][name]["sha256"] = runner._semantic_sha256(payload)
        record["fingerprint"]["exact_identity"] = True
    else:
        (Path(record["raw_dir"]) / "markers" / "probes_complete.json").unlink()
    record_path.write_text(json.dumps(record, allow_nan=False) + "\n", encoding="utf-8")
    result = checker.check_record(record_path, compact, SOURCE_SHA)
    assert not result["passed"]
    if mutation == "structural":
        assert result["classification"] == "CONTRACT_INVALID"


@pytest.mark.parametrize("field,value", (("rss", checker.COLD_LIMIT), ("retained", checker.RETAINED_LIMIT), ("swap", 1)))
def test_watchdog_resource_boundaries_fail_closed(tmp_path, field, value):
    record_path, compact_path, raw_path, record, compact = _valid_case(tmp_path)
    rows = [json.loads(line) for line in raw_path.read_text().splitlines()]
    if field == "rss":
        rows[0]["authority"]["process_tree"]["rss_bytes"] = value
    elif field == "retained":
        rows[-1]["authority"]["process_tree"]["rss_bytes"] = value
    else:
        rows[-1]["authority"]["process_tree"]["swap_bytes"] = value
    raw_path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    compact["raw_sha256"] = _sha(raw_path)
    compact["peak_process_tree_rss_bytes"] = max(row["authority"]["process_tree"]["rss_bytes"] for row in rows)
    compact["max_process_tree_swap_bytes"] = max(row["authority"]["process_tree"]["swap_bytes"] for row in rows)
    compact_path.write_text(json.dumps(compact) + "\n", encoding="utf-8")
    result = checker.check_record(record_path, compact_path, SOURCE_SHA)
    assert not result["passed"]


def test_runner_import_boundary_and_checker_imports():
    runner_path = ROOT / "benchmarks/run_task038_full3d_lor_hierarchy_capacity.py"
    tree = ast.parse(runner_path.read_text(encoding="utf-8"))
    top_imports = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            top_imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            top_imports.append(node.module)
    assert not any(name.startswith(("mpi4py", "petsc4py", "dolfinx", "src.solvers")) for name in top_imports)
    checker_path = ROOT / "benchmarks/task038_full3d_lor_hierarchy_capacity_checker.py"
    checker_tree = ast.parse(checker_path.read_text(encoding="utf-8"))
    imports = []
    for node in checker_tree.body:
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    assert not any(name.startswith(("benchmarks.run_task", "src.solvers", "petsc4py", "mpi4py")) for name in imports)


def test_cli_import_does_not_load_mpi():
    code = "import importlib,sys; importlib.import_module('benchmarks.run_task038_full3d_lor_hierarchy_capacity'); print(any(x.startswith(('mpi4py','petsc4py','dolfinx')) for x in sys.modules))"
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True)
    assert result.stdout.strip() == "False"


def test_runner_checker_semantic_hash_is_identical():
    payload = {"degree": 6, "matrix": {"rows": 8, "nnz": 16}, "semantic": "fixed"}
    assert runner._semantic_sha256(payload) == checker._semantic_sha256(payload)
    assert runner._semantic_sha256(payload) != hashlib.sha256(
        runner._semantic_bytes(payload) + b"\n"
    ).hexdigest()


def test_action_probe_executes_with_local_numpy_and_real_action_facts(monkeypatch):
    class FakeVec:
        def __init__(self):
            self.array = np.zeros(3, dtype=np.complex128)
            self.destroyed = False

        def getOwnershipRange(self):
            return 0, self.array.size

        def assemble(self):
            return None

        def getArray(self, readonly=True):
            return self.array

        def destroy(self):
            self.destroyed = True

    class FakeMatrix:
        def __init__(self):
            self.vectors = []

        def createVecRight(self):
            vector = FakeVec()
            self.vectors.append(vector)
            return vector

        def createVecLeft(self):
            vector = FakeVec()
            self.vectors.append(vector)
            return vector

        def mult(self, source, target):
            target.array[:] = 2.0 * source.array

    monkeypatch.setattr(
        runner, "_vector_digest", lambda vec: _digest(vec.getArray(readonly=True)), raising=False
    )
    matrix = FakeMatrix()
    arrays = {}
    facts = runner._action_probe(SimpleNamespace(degree=6, matrix=matrix), arrays)

    assert facts["finite"] is True
    assert facts["diff_norm"] == 0.0
    assert facts["input_unchanged"] is True
    assert set(arrays) == {"a6_input", "a6_out1", "a6_out2"}
    assert all(vector.destroyed for vector in matrix.vectors)


def test_transfer_probe_roundtrips_legal_coarse_primal_and_destroys_seeds(monkeypatch):
    class FakeVec:
        def __init__(self, owner):
            self.owner = owner
            self.array = np.zeros(3, dtype=np.complex128)
            self.destroy_count = 0

        def getOwnershipRange(self):
            return 0, self.array.size

        def getArray(self, readonly=True):
            return self.array

        def assemble(self):
            return None

        def destroy(self):
            self.destroy_count += 1

    class FakeMatrix:
        def __init__(self, owner):
            self.owner = owner
            self.vectors = []

        def _new(self):
            vector = FakeVec(self.owner)
            self.vectors.append(vector)
            return vector

        def createVecRight(self):
            return self._new()

        def createVecLeft(self):
            return self._new()

        def mult(self, source, target):
            target.array[:] = source.array

    class FakeLevel:
        def __init__(self, owner):
            self.matrix = FakeMatrix(owner)

        def primal_to_owner(self, source):
            assert source.array[1] != 0.0
            return np.array([source.array[0], source.array[2]], dtype=np.complex128)

        def owner_to_primal(self, packet):
            vector = self.matrix.createVecRight()
            vector.array[:] = (packet[0], 0.0, packet[1])
            return vector

    class FakeExtension:
        def __init__(self):
            self.levels = {1: FakeLevel("coarse"), 3: FakeLevel("fine")}

        def apply_primal(self, pair, source):
            assert source.array[1] == 0.0
            result = self.levels[pair[0]].matrix.createVecRight()
            result.array[:] = source.array
            return result

        def apply_adjoint(self, pair, source):
            result = self.levels[pair[1]].matrix.createVecRight()
            result.array[:] = source.array
            return result

    extension = FakeExtension()
    arrays = {}
    monkeypatch.setattr(
        runner, "_vector_digest", lambda vec: _digest(vec.getArray(readonly=True)), raising=False
    )
    facts = runner._transfer_probe(extension, (3, 1), arrays)

    assert facts["coarse_primal_source"] == runner.COARSE_PRIMAL_SOURCE
    assert facts["energy_relative"] == 0.0
    assert facts["finite"] is True
    assert all(vector.destroy_count == 1 for level in extension.levels.values() for vector in level.matrix.vectors)


def test_semantic_tree_nested_mapping_is_deterministic_and_rejects_object():
    value = {"b": (np.array([1, 2], dtype=np.int32), {"a": np.array([3.0], dtype=np.float64)})}
    first = runner._semantic_tree(value)
    second = runner._semantic_tree({"b": (np.array([1, 2], dtype=np.int32), {"a": np.array([3.0], dtype=np.float64)})})
    changed = runner._semantic_tree({"b": (np.array([1, 2], dtype=np.int32), {"a": np.array([4.0], dtype=np.float64)})})
    assert first == second
    assert first["sha256"] != changed["sha256"]
    assert first["kind"] == "mapping"
    with pytest.raises(TypeError, match="object dtype"):
        runner._semantic_tree(np.array([object()], dtype=object))


def test_missing_rebuild_array_is_contract_invalid_not_exception(tmp_path):
    record_path, compact, _watchdog_raw, record, _compact_value = _valid_case(tmp_path)
    raw_path = Path(record["raw_dir"])
    with np.load(raw_path / "probe_facts.npz", allow_pickle=False) as loaded:
        arrays = {key: loaded[key] for key in loaded.files if key != "rebuild_a6_out2"}
    np.savez(raw_path / "probe_facts.npz", **arrays)
    record["raw_artifacts"]["probe_npz"]["sha256"] = _sha(raw_path / "probe_facts.npz")
    record_path.write_text(json.dumps(record, allow_nan=False) + "\n", encoding="utf-8")
    result = checker.check_record(record_path, compact, SOURCE_SHA)
    assert result["classification"] == "CONTRACT_INVALID"
    assert any("rebuild_a6_out2" in error for error in result["contract_errors"])


def test_fingerprint_allocator_field_is_contract_invalid(tmp_path):
    record_path, compact, _raw, record, _compact_value = _valid_case(tmp_path)
    payload = record["fingerprint"]["first"]["payload"]
    payload["petsc_reported_memory_bytes"] = 0
    record["fingerprint"]["first"]["sha256"] = runner._semantic_sha256(payload)
    record_path.write_text(json.dumps(record, allow_nan=False) + "\n", encoding="utf-8")
    result = checker.check_record(record_path, compact, SOURCE_SHA)
    assert result["classification"] == "CONTRACT_INVALID"
    assert any("non-semantic field" in error for error in result["contract_errors"])


def test_fingerprint_payload_mismatch_is_algebra_gate(tmp_path):
    record_path, compact, _raw, record, _compact_value = _valid_case(tmp_path)
    payload = dict(record["fingerprint"]["rebuild"]["payload"])
    record["fingerprint"]["rebuild"]["payload"] = payload
    payload["semantic_variant"] = "changed"
    record["fingerprint"]["rebuild"]["sha256"] = runner._semantic_sha256(payload)
    record["fingerprint"]["exact_identity"] = False
    record_path.write_text(json.dumps(record, allow_nan=False) + "\n", encoding="utf-8")
    result = checker.check_record(record_path, compact, SOURCE_SHA)
    assert result["classification"] == "RESOURCE_OR_ALGEBRA_GATE_FAILED"
    assert not any("fingerprint" in error for error in result["contract_errors"])


def test_checker_strict_json_rejects_nonfinite(tmp_path):
    path = tmp_path / "nonfinite.json"
    path.write_text('{"value": NaN}\n', encoding="utf-8")
    with pytest.raises(ValueError):
        checker._read(path)


def _duplicate_dict_keys(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    duplicates: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        keys = [key.value for key in node.keys if isinstance(key, ast.Constant) and isinstance(key.value, str)]
        duplicates.extend(sorted({key for key in keys if keys.count(key) > 1}))
    return duplicates


def test_new_files_have_no_duplicate_dict_literals():
    paths = (
        ROOT / "benchmarks/run_task038_full3d_lor_hierarchy_capacity.py",
        ROOT / "benchmarks/task038_full3d_lor_hierarchy_capacity_checker.py",
        Path(__file__),
    )
    assert not [(str(path), key) for path in paths for key in _duplicate_dict_keys(path)]


def test_checker_output_is_fail_closed(tmp_path):
    record, compact, _raw, _record_value, _compact_value = _valid_case(tmp_path)
    output = tmp_path / "check.json"
    output.write_text("old\n", encoding="utf-8")
    with pytest.raises(FileExistsError):
        checker.main(["--record", str(record), "--watchdog-compact", str(compact),
                      "--expected-source-sha", SOURCE_SHA, "--output", str(output)])
