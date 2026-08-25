"""Pure-Python focused tests for the Review V12 R0 contract."""

from __future__ import annotations

import ast
import copy
import json
from pathlib import Path

import pytest

from src.solvers import fullspace_lor_interlevel_route_selection as contract
from benchmarks import task038_full3d_interlevel_route_selection_checker as checker


ROOT = Path(__file__).resolve().parents[2]
RECORD = ROOT / "docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/interlevel_route_selection_v1.json"


def _valid_measurement() -> dict[str, object]:
    return {
        "rank": 144,
        "hermitian_defect_b3": 1.0e-12,
        "hermitian_defect_g63": 1.0e-12,
        "strict_spd_b3": True,
        "strict_spd_g63": True,
        "minimum_eigenvalue_b3": 1.0,
        "minimum_eigenvalue_g63": 2.0,
        "endpoint_residual_min": 1.0e-10,
        "endpoint_residual_max": 1.0e-10,
        "lambda_min": 0.10,
        "lambda_max": 10.0,
        "condition": 100.0,
        "finite": True,
        "adjoint_work_relative": 1.0e-12,
        "linearity_relative": 1.0e-12,
        "repeat_relative": 1.0e-13,
        "input_unchanged": True,
        "phase_once": True,
        "probes": [
            {"name": name, "q": value, "finite": True, "input_unchanged": True}
            for name, value in zip(
                contract.PROBE_NAMES,
                (0.10, 1.0, 1.5, 2.0, 4.0, 10.0),
            )
        ],
    }


def test_route_a_gate_boundaries_and_independent_checker() -> None:
    facts = _valid_measurement()
    assert contract.check_route_a_measurement(facts)["passed"] is True
    assert checker.check_route_a_measurement(facts)["passed"] is True
    assert contract.check_route_a_measurement(facts)["derived_condition"] == 100.0
    assert checker.check_route_a_measurement(facts)["derived_condition"] == 100.0
    for key, value in (("rank", 143), ("lambda_min", 0.099999), ("lambda_max", 10.000001)):
        mutated = copy.deepcopy(facts)
        mutated[key] = value
        result = checker.check_route_a_measurement(mutated)
        assert result["passed"] is False
        assert result["gate_failures"]
    mismatch = copy.deepcopy(facts)
    mismatch["condition"] = 99.0
    mismatch_result = checker.check_route_a_measurement(mismatch)
    assert mismatch_result["passed"] is False
    assert mismatch_result["contract_errors"]


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("strict_spd_b3", False),
        ("strict_spd_g63", False),
        ("minimum_eigenvalue_b3", 0.0),
        ("minimum_eigenvalue_g63", 0.0),
        ("hermitian_defect_b3", 1.000001e-12),
        ("hermitian_defect_g63", 1.000001e-12),
        ("endpoint_residual_min", 1.000001e-10),
        ("endpoint_residual_max", 1.000001e-10),
        ("adjoint_work_relative", 1.000001e-12),
        ("linearity_relative", 1.000001e-12),
        ("repeat_relative", 1.000001e-13),
        ("finite", False),
        ("input_unchanged", False),
        ("phase_once", False),
    ),
)
def test_route_a_legality_and_spectral_gate_boundaries(field: str, value: object) -> None:
    facts = _valid_measurement()
    facts[field] = value
    result = checker.check_route_a_measurement(facts)
    assert result["passed"] is False
    assert result["gate_failures"]


def test_route_a_six_probe_boundaries() -> None:
    facts = _valid_measurement()
    assert checker.check_route_a_measurement(facts)["passed"] is True
    mutated = copy.deepcopy(facts)
    mutated["probes"][5]["q"] = 10.000001  # type: ignore[index]
    result = checker.check_route_a_measurement(mutated)
    assert result["passed"] is False
    assert any("range" in item for item in result["gate_failures"])
    wrong_identity = copy.deepcopy(facts)
    wrong_identity["probes"][0]["name"] = "gradient"  # type: ignore[index]
    identity_result = checker.check_route_a_measurement(wrong_identity)
    assert identity_result["passed"] is False
    assert identity_result["contract_errors"]


def test_route_a_measurement_missing_key_is_contract_error() -> None:
    facts = _valid_measurement()
    del facts["adjoint_work_relative"]
    result = checker.check_route_a_measurement(facts)
    assert result["passed"] is False
    assert result["contract_errors"]
    nonfinite = _valid_measurement()
    nonfinite["lambda_min"] = float("nan")
    nonfinite_result = checker.check_route_a_measurement(nonfinite)
    assert nonfinite_result["passed"] is False
    assert nonfinite_result["contract_errors"]


def test_missing_key_is_contract_error(tmp_path: Path) -> None:
    record = json.loads(RECORD.read_text(encoding="utf-8"))
    del record["route_a"]["rank"]
    path = tmp_path / "missing.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    result = checker.check_record(path, checker.SOURCE_SHA)
    assert result["status"] == "CONTRACT_INVALID"
    assert result["contract_errors"]


def test_nonfinite_json_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "nonfinite.json"
    path.write_text('{"value": NaN}\n', encoding="utf-8")
    result = checker.check_record(path, checker.SOURCE_SHA)
    assert result["status"] == "CONTRACT_INVALID"
    assert "strict JSON" in result["contract_errors"][0]


def test_frozen_manifest_and_old_s5_status_hashes() -> None:
    result = checker.check_record(RECORD, checker.SOURCE_SHA)
    assert result["status"] == "CONTRACT_READY"
    assert result["classification"] == "CONTRACT_READY_MEASURED_NOT_RUN"
    manifest = json.loads(RECORD.read_text(encoding="utf-8"))
    assert manifest["preserved_v11_s5"]["energy_gate_limit"] == 1.0e-9
    assert manifest["preserved_v11_s5"]["status"] == "RESOURCE_OR_ALGEBRA_GATE_FAILED"
    assert manifest["route_a"]["status"] == "not_run"
    assert manifest["execution"]["r1_spectrum"] == "not_run"
    assert manifest["route_a"]["probe_names"] == list(contract.PROBE_NAMES)
    assert "class_digest" in manifest["route_a"]["material_class_required_fields"]
    s4 = next(item for item in manifest["frozen_evidence"] if item["name"] == "v11_s4_oracle_pass")
    assert all("aggregate_check.json" not in item["path"] for item in s4["artifacts"])
    assert s4["source_aggregate"]["availability"] == "ignored_raw_digest_preserved_indirectly"


def test_fixed_route_transitions_do_not_run_b_or_c() -> None:
    assert contract.next_route_after_route_a(False) == "B"
    assert contract.next_route_after_route_a(True) == "R2"
    with pytest.raises(TypeError):
        contract.next_route_after_route_a(1)  # type: ignore[arg-type]


def test_checker_has_no_solver_or_mpi_import() -> None:
    tree = ast.parse(Path(checker.__file__).read_text(encoding="utf-8"))
    forbidden = ("runner", "solver", "petsc", "mpi", "dolfinx")
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name.lower() for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module.lower())
    assert not any(any(token in name for token in forbidden) for name in imported)


def test_new_python_files_have_no_duplicate_literal_keys() -> None:
    paths = (
        ROOT / "src/solvers/fullspace_lor_interlevel_route_selection.py",
        ROOT / "benchmarks/task038_full3d_interlevel_route_selection_checker.py",
        Path(__file__),
    )
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            keys = [key.value for key in node.keys if isinstance(key, ast.Constant) and isinstance(key.value, str)]
            assert len(keys) == len(set(keys)), f"duplicate dict key in {path}"
