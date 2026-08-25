"""Independent pure-data checker for the Review V12 R0 route contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

SCHEMA = "task038.full3d.interlevel-route-selection.v1"
SOURCE_SHA = "9a5015fa04cc92a586baa20a19608af1d0131327"
BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
INPUT_PATH = "input/templates/full3d_iterative_example.dat"
INPUT_SHA = "819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41"
RESOLVED_SHA = "78dc49b3a7ae212dec6374fde09eaaa231c131ce64790202da062b3ca2b09aad"
PHYSICAL_SHA = "9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f"
RANK = 144
HERMITIAN_LIMIT = 1.0e-12
ENDPOINT_RESIDUAL_LIMIT = 1.0e-10
LAMBDA_MIN_LIMIT = 0.10
LAMBDA_MAX_LIMIT = 10.0
CONDITION_LIMIT = 100.0
PROBE_COUNT = 6
PROBE_MIN = 0.10
PROBE_MAX = 10.0
PROBE_NAMES = (
    "random",
    "gradient",
    "curl",
    "checkerboard",
    "physical_component_derived",
    "r3_long_tail_derived",
)
ADJOINT_LIMIT = 1.0e-12
LINEARITY_LIMIT = 1.0e-12
REPEAT_LIMIT = 1.0e-13
CONDITION_CLOSE_TOL = 1.0e-12
MATERIAL_CLASS_REQUIRED_FIELDS = (
    "class_digest",
    "material_coefficient_identity",
    "geometry_jacobian_identity",
    "rank",
    "sigma_min",
    "sigma_max",
    "hermitian_defect_b3",
    "hermitian_defect_g63",
    "minimum_eigenvalue_b3",
    "minimum_eigenvalue_g63",
    "lambda_min",
    "lambda_max",
    "spectral_condition",
    "endpoint_residual_min",
    "endpoint_residual_max",
    "finite",
)
REPO_ROOT = Path(__file__).resolve().parents[1]


FROZEN_EVIDENCE = (
    {
        "name": "v10_q0_reference_triage",
        "status": "controlled_negative",
        "artifacts": (
            ("docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/p3_exact_reference_triage_v1.json", "2d767143ce3b28ac9a4b45962faf370770e1e637f05b4f0b62bb279fe7f6ca82"),
            ("docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/p3_exact_reference_triage_v1_checker.json", "be70e0e559fea32023dfde58e4ede11009574c18f51e4b914d9b5034832a35ea"),
        ),
    },
    {
        "name": "foundation_e_3020_pass",
        "status": "pass",
        "artifacts": (
            ("docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/p3_exact_edge_foundation_10000_v1.json", "ab98d01a99d22e69fd2ed9132bf64d8703e30ff4589a3120e17ed31a6d7beac0"),
            ("docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/p3_exact_edge_foundation_10000_v1_checker_v2.json", "b42675cc9b3d6729f18c1ae744742fefbfe312ded30b5db2ada098664db98525"),
            ("docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/p3_exact_edge_foundation_10000_v1_watchdog.json", "9c08f9f94073fb53c335c143829672b24bb0dad402d5199eea26efc6d01800cc"),
        ),
    },
    {
        "name": "old_slepc_nonconvergence",
        "status": "controlled_negative",
        "artifacts": (
            ("docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/p3_global_lor_spectral_audit_v1_failure.json", "595779b0997f2631a2abb6f78fec739767a4c2a944c34eb61a31d11d116607a6"),
            ("docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/p3_global_lor_spectral_audit_v1_watchdog.json", "55e2ae1299eace079aaf943422acd912052b869d5eaaaa147a88c9ad3142b9c3"),
        ),
    },
    {
        "name": "hx_pcgamg_closure",
        "status": "closed",
        "artifacts": (
            ("docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/lor_native_complex_hx_oracle_v1.json", "eaea740a3b379066204f9b4055e217718305a708d912cc2cdd9ba72339672f50"),
            ("docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/lor_native_complex_hx_krylov_pc_additive_v2_campaign_v1.json", "55801084cd59659d66a4e05b048340e038105d533e0c60667fd8558dc4988f2c"),
        ),
    },
    {
        "name": "v11_s1_global_spectral_pass",
        "status": "pass",
        "artifacts": (
            ("docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/lor_global_spectral_audit_v2.json", "8ffa8f1e74392bbd062314e0656d56c3bc464520c541d3a4668a52fad0a2ab09"),
            ("docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/lor_global_spectral_audit_v2_checker.json", "acec3b84f2e8001335bf362aa509e5a809657d5af11b33a847e51fd63cf1a5e3"),
        ),
    },
    {
        "name": "v11_s2_resource_pass",
        "status": "pass",
        "artifacts": (
            ("docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/lor_p6h10_foundation_resource_v1.json", "70f8f865a8943297364fdb2fdcbcbf164ceb4f56af8c48285bcca5f8af196a24"),
            ("docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/lor_p6h10_foundation_resource_v1_checker.json", "4f6834a02948fb8d86031ce609d467889a70bef3f143cb1c2f2c1af78cc5605a"),
        ),
    },
    {
        "name": "v11_s4_oracle_pass",
        "status": "pass_small_oracle_scope",
        "artifacts": (
            ("docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/lor_edge_geometric_mg_oracle_v1.json", "5d132e21915c1a3fb1fa9af0c1fe3a4b711005b8bdedac08e04ee56b96b1cfb6"),
            ("docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/lor_edge_geometric_mg_oracle_v1_checker.json", "8e2b552fbc773bda94d2605a5a8184e1d3ee35929964e84903a80c1fa39bb38b"),
        ),
        "source_aggregate": {
            "path": "benchmarks/artifacts/task038_extra_full3d_lor_edge_geometric_mg_v1/2b2df645418ee28c68681832661e58993897166d/aggregate_check.json",
            "sha256": "56b7eec1435abc69a38c38af056d8803e8f62a3ff6768b87faa594670c916c4e",
            "availability": "ignored_raw_digest_preserved_indirectly",
        },
    },
    {
        "name": "v11_s5_exact_energy_gate_failure",
        "status": "failed_algebra_gate",
        "artifacts": (
            ("docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/lor_edge_geometric_mg_p6_capacity_v1.json", "2a2731325cc0fc75b5efb1445c812e0660b4987b96ad88de2a471d623887e181"),
            ("docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/lor_edge_geometric_mg_p6_capacity_v1_checker.json", "cb74710a144aac0db18741c6328fe4ec2b25e61c9535c6c0d4c1ec686f108221"),
        ),
    },
    {
        "name": "ba40358_probe_domain_invalid",
        "status": "controlled_negative_probe_domain_invalid",
        "artifacts": (
            ("docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/lor_edge_geometric_mg_p6_capacity_v1_probe_invalid_ba40358.json", "ad8bbc3dfd81ba489efd6a4b2c24530c43f68484facc43020f9c5044f3be2a3f"),
            ("docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/lor_edge_geometric_mg_p6_capacity_v1_checker_probe_invalid_ba40358.json", "93423f917256edd40ac13727af2feac58e4dcc63dde29a229742e6b960f5aaa8"),
        ),
    },
)


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant: {value}")


def _finite_tree(value: Any) -> bool:
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _finite_tree(child) for key, child in value.items())
    if isinstance(value, list):
        return all(_finite_tree(child) for child in value)
    return True


def _read_json(path: Path) -> tuple[Any | None, str | None]:
    try:
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle, parse_constant=_reject_constant)
    except Exception as exc:  # malformed input is a contract result, not a checker crash
        return None, f"cannot read strict JSON {path}: {exc}"
    if not _finite_tree(value):
        return None, f"non-finite JSON value in {path}"
    return value, None


def _finite_number(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(float(value))


def _file_sha256(relative_path: str) -> str | None:
    path = REPO_ROOT / relative_path
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def check_route_a_measurement(facts: Any) -> dict[str, Any]:
    """Independent Route A measurement check; no solver or source import."""

    contract_errors: list[str] = []
    gate_failures: list[str] = []
    derived_condition: float | None = None
    required = (
        "rank", "hermitian_defect_b3", "hermitian_defect_g63",
        "strict_spd_b3", "strict_spd_g63", "endpoint_residual_min",
        "endpoint_residual_max", "lambda_min", "lambda_max", "condition",
        "minimum_eigenvalue_b3", "minimum_eigenvalue_g63",
        "finite", "adjoint_work_relative", "linearity_relative",
        "repeat_relative", "input_unchanged", "phase_once", "probes",
    )
    if not isinstance(facts, dict):
        return {"passed": False, "contract_errors": ["measurement is not an object"], "gate_failures": []}
    missing = [key for key in required if key not in facts]
    if missing:
        return {"passed": False, "contract_errors": [f"missing measurement field: {key}" for key in missing], "gate_failures": []}
    if type(facts["rank"]) is not int:
        contract_errors.append("rank must be int")
    elif facts["rank"] != RANK:
        gate_failures.append("rank gate")
    for key in ("hermitian_defect_b3", "hermitian_defect_g63"):
        value = facts[key]
        if not _finite_number(value):
            contract_errors.append(f"{key} must be finite")
        elif float(value) > HERMITIAN_LIMIT:
            gate_failures.append(f"{key} gate")
    for key in ("endpoint_residual_min", "endpoint_residual_max"):
        value = facts[key]
        if not _finite_number(value):
            contract_errors.append(f"{key} must be finite")
        elif float(value) > ENDPOINT_RESIDUAL_LIMIT:
            gate_failures.append(f"{key} gate")
    for key in ("minimum_eigenvalue_b3", "minimum_eigenvalue_g63"):
        value = facts[key]
        if not _finite_number(value):
            contract_errors.append(f"{key} must be finite")
        elif float(value) <= 0.0:
            gate_failures.append(f"{key} positivity gate")
    for key, lower, upper in (
        ("lambda_min", LAMBDA_MIN_LIMIT, None),
        ("lambda_max", None, LAMBDA_MAX_LIMIT),
        ("condition", None, None),
    ):
        value = facts[key]
        if not _finite_number(value):
            contract_errors.append(f"{key} must be finite")
        elif lower is not None and float(value) < lower:
            gate_failures.append(f"{key} lower gate")
        elif upper is not None and float(value) > upper:
            gate_failures.append(f"{key} upper gate")
    lambda_min = facts["lambda_min"]
    lambda_max = facts["lambda_max"]
    reported_condition = facts["condition"]
    if _finite_number(lambda_min) and _finite_number(lambda_max) and _finite_number(reported_condition):
        if float(lambda_min) <= 0.0:
            gate_failures.append("lambda_min must be positive for derived condition")
        else:
            derived_condition = float(lambda_max) / float(lambda_min)
            if derived_condition > CONDITION_LIMIT:
                gate_failures.append("derived condition upper gate")
            if not math.isclose(
                float(reported_condition),
                derived_condition,
                rel_tol=CONDITION_CLOSE_TOL,
                abs_tol=CONDITION_CLOSE_TOL,
            ):
                contract_errors.append("reported condition does not match lambda ratio")
    for key in ("strict_spd_b3", "strict_spd_g63", "finite", "input_unchanged", "phase_once"):
        if type(facts[key]) is not bool:
            contract_errors.append(f"{key} must be bool")
        elif not facts[key]:
            gate_failures.append(f"{key} gate")
    for key, limit in (("adjoint_work_relative", ADJOINT_LIMIT), ("linearity_relative", LINEARITY_LIMIT), ("repeat_relative", REPEAT_LIMIT)):
        value = facts[key]
        if not _finite_number(value):
            contract_errors.append(f"{key} must be finite")
        elif float(value) > limit:
            gate_failures.append(f"{key} gate")
    probes = facts["probes"]
    if not isinstance(probes, list) or len(probes) != PROBE_COUNT:
        contract_errors.append(f"probes must have {PROBE_COUNT} entries")
    else:
        names: list[str] = []
        for index, probe in enumerate(probes):
            if not isinstance(probe, dict):
                contract_errors.append(f"probe {index} is not an object")
                continue
            if not all(key in probe for key in ("name", "q", "finite", "input_unchanged")):
                contract_errors.append(f"probe {index} fields incomplete")
                continue
            if type(probe["name"]) is not str:
                contract_errors.append(f"probe {index} name must be string")
            else:
                names.append(probe["name"])
            if not _finite_number(probe["q"]):
                contract_errors.append(f"probe {index} q must be finite")
            elif not PROBE_MIN <= float(probe["q"]) <= PROBE_MAX:
                gate_failures.append(f"probe {index} range gate")
            for key in ("finite", "input_unchanged"):
                if type(probe[key]) is not bool:
                    contract_errors.append(f"probe {index} {key} must be bool")
                elif not probe[key]:
                    gate_failures.append(f"probe {index} {key} gate")
        if len(names) == PROBE_COUNT and names != list(PROBE_NAMES):
            contract_errors.append("probe names/order do not match frozen identities")
    return {
        "passed": not contract_errors and not gate_failures,
        "contract_errors": contract_errors,
        "gate_failures": gate_failures,
        "derived_condition": derived_condition,
    }


def _check_evidence(record: dict[str, Any], errors: list[str]) -> None:
    actual = record.get("frozen_evidence")
    if not isinstance(actual, list):
        errors.append("frozen_evidence must be a list")
        return
    expected_names = {item["name"] for item in FROZEN_EVIDENCE}
    actual_names = [item.get("name") if isinstance(item, dict) else None for item in actual]
    if set(actual_names) != expected_names or len(actual_names) != len(expected_names):
        errors.append("frozen evidence names are not the fixed set")
    for expected in FROZEN_EVIDENCE:
        matches = [item for item in actual if isinstance(item, dict) and item.get("name") == expected["name"]]
        if len(matches) != 1:
            errors.append(f"missing or duplicate evidence: {expected['name']}")
            continue
        item = matches[0]
        if item.get("status") != expected["status"] or item.get("immutable") is not True:
            errors.append(f"evidence status/immutability mismatch: {expected['name']}")
        expected_artifacts = [{"path": path, "sha256": sha} for path, sha in expected["artifacts"]]
        if item.get("artifacts") != expected_artifacts:
            errors.append(f"evidence artifact descriptors mismatch: {expected['name']}")
        if expected.get("source_aggregate") is not None and item.get("source_aggregate") != expected["source_aggregate"]:
            errors.append(f"source aggregate descriptor mismatch: {expected['name']}")
        for path, expected_sha in expected["artifacts"]:
            actual_sha = _file_sha256(path)
            if actual_sha != expected_sha:
                errors.append(f"evidence hash mismatch: {path}")


def check_record(record_path: str | Path, expected_source_sha: str) -> dict[str, Any]:
    """Return a derived R0 contract result without trusting record status."""

    path = Path(record_path)
    record, read_error = _read_json(path)
    if read_error is not None:
        return {"schema": SCHEMA, "status": "CONTRACT_INVALID", "classification": "CONTRACT_INVALID", "contract_errors": [read_error], "gate_failures": []}
    errors: list[str] = []
    if not isinstance(record, dict):
        errors.append("record must be an object")
        record = {}
    if record.get("schema") != SCHEMA:
        errors.append("schema mismatch")
    if record.get("stage") != "r0":
        errors.append("stage must be r0")
    if record.get("status") != "CONTRACT_READY":
        errors.append("record status must remain CONTRACT_READY")
    if record.get("classification") != "CONTRACT_READY_MEASURED_NOT_RUN":
        errors.append("record classification must remain measured-not-run")
    provenance = record.get("provenance")
    if not isinstance(provenance, dict):
        errors.append("provenance must be an object")
    else:
        if provenance.get("branch") != BRANCH:
            errors.append("branch mismatch")
        if provenance.get("source_sha") != expected_source_sha or expected_source_sha != SOURCE_SHA:
            errors.append("source SHA mismatch")
        expected_input = {
            "path_relative": INPUT_PATH,
            "raw_bytes": 2119,
            "raw_sha256": INPUT_SHA,
            "resolved_bytes": 4076,
            "resolved_sha256": RESOLVED_SHA,
            "physical_model_sha256": PHYSICAL_SHA,
        }
        if provenance.get("input_identity") != expected_input:
            errors.append("input identity mismatch")
    if record.get("route_order") != ["A", "B", "C"]:
        errors.append("route order mismatch")
    route_a = record.get("route_a")
    expected_route_a = {
        "name": "p6_to_p3_spectrum_route",
        "rank": RANK,
        "hermitian_limit": HERMITIAN_LIMIT,
        "endpoint_residual_limit": ENDPOINT_RESIDUAL_LIMIT,
        "lambda_min_limit": LAMBDA_MIN_LIMIT,
        "lambda_max_limit": LAMBDA_MAX_LIMIT,
        "condition_limit": CONDITION_LIMIT,
        "probe_count": PROBE_COUNT,
        "probe_q_interval": [PROBE_MIN, PROBE_MAX],
        "probe_names": list(PROBE_NAMES),
        "material_class_required_fields": list(MATERIAL_CLASS_REQUIRED_FIELDS),
        "status": "not_run",
        "measurement_scope": "R1_not_authorized",
    }
    if route_a != expected_route_a:
        errors.append("Route A prospective contract mismatch")
    for key in ("route_b", "route_c"):
        route = record.get(key)
        if not isinstance(route, dict) or route.get("status") != "conditional_not_run" or route.get("implemented") is not False:
            errors.append(f"{key} must be conditional_not_run and unimplemented")
    execution = record.get("execution")
    if execution != {"r1_spectrum": "not_run", "r2_positive": "not_run", "heavy_formal": "not_run"}:
        errors.append("execution boundary mismatch")
    if record.get("raw_artifacts") != []:
        errors.append("R0 must not claim raw R1 artifacts")
    old_s5 = record.get("preserved_v11_s5")
    expected_old_s5 = {
        "record_sha256": "2a2731325cc0fc75b5efb1445c812e0660b4987b96ad88de2a471d623887e181",
        "checker_sha256": "cb74710a144aac0db18741c6328fe4ec2b25e61c9535c6c0d4c1ec686f108221",
        "energy_gate_limit": 1.0e-9,
        "energy_6_to_3": 0.04115402900674629,
        "energy_3_to_1": 2.7851655955739857e-15,
        "status": "RESOURCE_OR_ALGEBRA_GATE_FAILED",
        "preserved_without_modification": True,
    }
    if old_s5 != expected_old_s5:
        errors.append("V11 S5 preservation contract mismatch")
    _check_evidence(record, errors)
    if record.get("route_decision_contract") != {"route_a_fail": "B", "route_a_pass": "R2"}:
        errors.append("route decision contract mismatch")
    classification = "CONTRACT_READY_MEASURED_NOT_RUN" if not errors else "CONTRACT_INVALID"
    return {
        "schema": SCHEMA,
        "status": "CONTRACT_READY" if not errors else "CONTRACT_INVALID",
        "classification": classification,
        "contract_errors": errors,
        "gate_failures": [],
        "route_a_status": "not_run",
        "route_a_passed": None,
        "route_decision_if_measured": {"fail": "B", "pass": "R2"},
        "frozen_evidence_verified": not errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--expected-source-sha", required=True)
    args = parser.parse_args(argv)
    output = Path(args.output)
    if output.exists():
        raise SystemExit(f"refusing to overwrite checker output: {output}")
    result = check_record(args.record, args.expected_source_sha)
    output.write_text(json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return 0 if not result["contract_errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
