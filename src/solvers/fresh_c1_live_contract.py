"""Fresh C1 same-live qualification wrapper for the isolated p6 component.

The numerical proof lives in :mod:`dtn_boundary_plane_qualification`; this
module binds that proof to one unchanged live carrier before and after the
worker.  It deliberately has no y-orbit, quotient, solver, or PDE import.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Callable, Mapping

from .dtn_boundary_plane_qualification import (
    BOUNDARY_PLANE,
    LIVE_COMPONENT_GATES,
    carrier_numeric_identity,
    qualify_fresh_c1_p6_boundary_plane_bundle,
    validate_fresh_c1_bundle_profile,
)
from .fresh_c1_manifest_identity import (
    NATIVE_LINUX_PROFILE,
    NATIVE_LITERAL532_MANIFEST_SHA256,
    literal532_manifest_sha256,
)


PHYSICAL_GENERATOR_SHA256 = NATIVE_LITERAL532_MANIFEST_SHA256
LIVE_RECEIPT_SCHEMA = "task40extra.same-live-boundary-component.v1"


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_plain(value: Any) -> Any:
    """Normalize frozen mappings/tuples and NumPy scalars like the receipt writer."""
    if isinstance(value, Mapping):
        return {str(key): _json_plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_plain(item) for item in value]
    if isinstance(value, complex):
        return {"real": float(value.real), "imag": float(value.imag)}
    if isinstance(value, (str, bool, int, float)) or value is None:
        return value
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        return _json_plain(tolist())
    item = getattr(value, "item", None)
    if callable(item):
        return _json_plain(item())
    raise TypeError(f"unsupported receipt value type: {type(value).__name__}")


def _validate_ordered_mode_identity(identity: Mapping[str, Any], modes: Any) -> list[Any]:
    """Validate the serialized literal532 key sequence and its per-mode ledger."""
    keys = identity.get("ordered_mode_keys")
    if not isinstance(keys, list) or len(keys) != 532 or len({tuple(key) for key in keys}) != 532:
        raise ValueError("same-live receipt ordered mode identity is incomplete or repeated")
    for index, item in enumerate(modes):
        if (not isinstance(item, dict) or item.get("index") != index or item.get("key") != keys[index]
                or len(item.get("key", [])) != 5
                or keys[index][0] != index or keys[index][1] not in {"top", "bottom"}
                or type(keys[index][2]) is not int or type(keys[index][3]) is not int
                or keys[index][4] not in {"s", "p", "x", "y"}):
            raise ValueError("same-live literal532 mode key order changed")
    return keys


def validate_live_receipt(receipt: Mapping[str, Any], *, identity: Mapping[str, Any],
                          runtime_profile: str | None = None) -> None:
    """Recheck the complete saved numeric ledger before admitting a worker."""
    receipt = _json_plain(receipt)
    json_identity = _json_plain(identity)
    if runtime_profile is None:
        runtime_profile = receipt.get("runtime_profile", NATIVE_LINUX_PROFILE)
    expected_physical = literal532_manifest_sha256(runtime_profile)
    if (receipt.get("schema") != LIVE_RECEIPT_SCHEMA
            or receipt.get("status") != "PASS_COMPONENT_ONLY"
            or receipt.get("full_case_pass") is not True
            or receipt.get("PDE_solved") is not False
            or receipt.get("official_results") is not False
            or receipt.get("runtime_profile", NATIVE_LINUX_PROFILE) != runtime_profile
            or receipt.get("physical_generator_manifest_sha256") != expected_physical
            or identity.get("physical_generator_manifest_sha256") != expected_physical
            or json.loads(json.dumps(receipt.get("identity"))) != json_identity
            or receipt.get("carrier_digest_before") != identity.get("carrier_numeric_sha256")
            or receipt.get("carrier_digest_after") != identity.get("carrier_numeric_sha256")
            or receipt.get("degree") != 6
            or receipt.get("fresh_fixture_c1") is not True
            or receipt.get("mode_count") != 532
            or receipt.get("completed_gates") != list(LIVE_COMPONENT_GATES)
            or len(receipt.get("per_mode", ())) != 532
            or len(receipt.get("output_component_gates", ())) != 5):
        raise ValueError("fresh p6 requires a complete same-live fresh-C1 literal532 receipt")
    profile = receipt.get("fresh_c1_profile")
    actual = receipt.get("fresh_c1_actual_inventory")
    expected_profile = {
        "degree": 6, "cell_count": 80, "local_space_dimension": 882,
        "local_interior_rows": 450, "local_trace_rows": 432, "storage_rows": 55950,
        "independent_rows": 52992, "interior_rows": 36000,
        "independent_trace_rows": 16992, "native_slave_rows": 2958,
        "quadrature_degree": 27, "primary_facet_points": 196,
        "mode_count": 532, "manual_M": 9, "manual_N": 3,
        "runtime_profile": runtime_profile,
        "physical_generator_manifest_sha256": expected_physical,
    }
    if runtime_profile == NATIVE_LINUX_PROFILE:
        expected_profile.pop("runtime_profile")
    actual_profile = {name: profile.get(name) if isinstance(profile, dict) else None
                      for name in expected_profile}
    actual_inventory = {name: actual.get(name) if isinstance(actual, dict) else None
                       for name in ("cell_count", "local_space_dimension", "local_interior_rows",
                                    "local_trace_rows", "storage_rows", "independent_rows",
                                    "interior_rows", "independent_trace_rows", "native_slave_rows")}
    expected_inventory = {name: expected_profile[name] for name in actual_inventory}
    if (actual_profile != expected_profile or actual_inventory != expected_inventory
            or profile.get("p6_full_chain_qualified") is not False
            or profile.get("compact_p4_quotient_qualified") is not False
            or receipt.get("degree") != 6 or receipt.get("element_degree") != 6
            or receipt.get("fresh_fixture_c1") is not True
            or receipt.get("mode_count") != 532
            ):
        raise ValueError("same-live receipt p6 profile differs from the exact fresh80 contract")
    tolerance, seed = receipt.get("tolerance"), receipt.get("seed")
    if type(tolerance) not in (int, float) or float(tolerance) != 1.0e-10 or seed != 4053202:
        raise ValueError("same-live receipt changed the frozen literal532 tolerance or RNG seed")

    def finite_number(value: Any, label: str, *, maximum: float | None = None,
                      minimum: float | None = None) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"same-live receipt lacks numeric {label}")
        number = float(value)
        if not math.isfinite(number) or (maximum is not None and number > maximum) \
                or (minimum is not None and number < minimum):
            raise ValueError(f"same-live receipt fails numeric {label}")
        return number

    discrete_context = receipt.get("raw_discrete_context")
    try:
        context_sha = hashlib.sha256(json.dumps(
            discrete_context, sort_keys=True, separators=(",", ":"),
            allow_nan=False, ensure_ascii=True).encode("ascii")).hexdigest()
    except (TypeError, ValueError) as error:
        raise ValueError("same-live receipt discrete context is not canonical JSON") from error
    if (not isinstance(discrete_context, dict)
            or context_sha != identity.get("assembly_context_sha256")
            or discrete_context.get("schema") != "task40extra.dtn-plane-discrete-context.v1"
            or discrete_context.get("element_degree") != 6
            or discrete_context.get("element_map_type") != "covariantPiola"
            or receipt.get("assembly_context_sha256") != context_sha
            or receipt.get("assembly_mode_manifest_sha256") != identity.get("assembly_mode_manifest_sha256")):
        raise ValueError("same-live receipt does not bind the canonical assembly context")
    context_abi = discrete_context.get("ABI", {})
    if (context_abi.get("scalar") != "complex128" or context_abi.get("integer") != "int32"
            or context_abi.get("dolfinx_mpc") != "0.10.5"
            or list(context_abi.get("PETSc", ())) != [3, 25, 6]):
        raise ValueError("same-live receipt ABI differs from the native p6 contract")

    if (receipt.get("qualification_source_sha256")
            != file_sha256(Path(__file__).with_name("dtn_boundary_plane_qualification.py"))):
        raise ValueError("same-live receipt qualification source differs from this checkout")
    if (receipt.get("primary_compiled_gauss")
            != discrete_context.get("gauss", {}).get("compiled_forms_verified")
            or receipt.get("quadrature_degree") != discrete_context.get("gauss", {}).get("degree")):
        raise ValueError("same-live primary compiled Gauss record differs from its canonical context")
    primary = receipt.get("primary_compiled_gauss")
    oracle = receipt.get("independent_oracle_compiled_gauss")
    expected_primary = {f"{side}/{component}" for side in ("top", "bottom") for component in (0, 1)}
    expected_oracle = {f"{gauge}/{side}/{component}" for gauge in ("global_z", "boundary_plane")
                       for side in ("top", "bottom") for component in (0, 1)}
    if not isinstance(primary, dict) or set(primary) != expected_primary \
            or not isinstance(oracle, dict) or set(oracle) != expected_oracle:
        raise ValueError("same-live receipt must retain all four primary and eight independent Gauss identities")

    def verify_gauss(record: Any, label: str) -> None:
        if not isinstance(record, dict) or not isinstance(record.get("rules"), list) \
                or not record["rules"] or not isinstance(record.get("compiled_C_sha256"), str):
            raise ValueError(f"same-live {label} Gauss record is incomplete")
        for rule in record["rules"]:
            if (not isinstance(rule, dict) or rule.get("integral_type") != "exterior_facet"
                    or not isinstance(rule.get("degree"), int)
                    or not isinstance(rule.get("points"), dict)
                    or not isinstance(rule.get("weights"), dict)
                    or rule.get("compiled_weight_tables_verified", 0) < 1):
                raise ValueError(f"same-live {label} Gauss record lacks analyzed nodes/weights provenance")
        kernel = record.get("loaded_kernel")
        if kernel is not None:
            if (kernel.get("restoration_exact") is not True
                    or kernel.get("numerical_assembly_during_probe") is not False
                    or kernel.get("num_constants") != 3
                    or [item.get("role") for item in kernel.get("constant_roles", [])]
                    != ["alpha", "gamma", "kz"]):
                raise ValueError(f"same-live {label} loaded-kernel restoration/probe gate failed")
            for path_key, hash_key in (("module_path", "binary_sha256"),
                                       ("module_bound_C_path", "module_bound_C_sha256")):
                path = Path(kernel.get(path_key, ""))
                if (not path.is_file() or not isinstance(kernel.get(hash_key), str)
                        or file_sha256(path) != kernel[hash_key]):
                    raise ValueError(f"same-live {label} loaded binary/source provenance differs")
    for key, record in primary.items():
        verify_gauss(record, "primary/" + key)
        if "loaded_kernel" not in record:
            raise ValueError("same-live primary Gauss record lacks loaded-kernel proof")
    for key, record in oracle.items():
        verify_gauss(record, "independent/" + key)
        _gauge, side, component = key.split("/")
        if record["rules"] != primary[f"{side}/{component}"]["rules"]:
            raise ValueError("same-live independent Gauss nodes/weights differ from primary")
    verify_gauss(receipt.get("incident_literal_gauss"), "incident FE RHS")
    if receipt["incident_literal_gauss"]["rules"] != primary["top/0"]["rules"]:
        raise ValueError("same-live literal incident form uses a different compiled Gauss rule")

    tolerance = float(tolerance)
    modes = receipt["per_mode"]
    _validate_ordered_mode_identity(json_identity, modes)
    for index, item in enumerate(modes):
        equivalence = item.get("equivalence")
        if not isinstance(equivalence, dict):
            raise ValueError("same-live mode lacks raw coefficient/action equivalence metrics")
        for name in ("raw_C_equivalence", "raw_D_equivalence", "raw_H_equivalence",
                     "per_mode_raw_action_equivalence"):
            finite_number(equivalence.get(name), f"mode {index} {name}", maximum=tolerance)
        finite_number(item.get("new_stored_relative_operator_bound"),
                      f"mode {index} all-DOF rank-one bound", maximum=tolerance)
        finite_number(item.get("raw_nonzero_port_equation_defect"),
                      f"mode {index} raw port equation", maximum=tolerance)
        finite_number(item.get("power_operation_scaled_defect"),
                      f"mode {index} power equivalence", maximum=tolerance)
        for field in ("Hglobal", "Hplane", "raw_C_norm", "raw_D_norm"):
            finite_number(item.get(field), f"mode {index} {field}", minimum=0.0)
        for name in ("raw_recovery_operation_scaled_defects", "production_recovery_operation_scaled_defects"):
            defects = item.get(name)
            if not isinstance(defects, list) or len(defects) != 5:
                raise ValueError(f"same-live mode {index} lacks all five {name}")
            for column, defect in enumerate(defects):
                finite_number(defect, f"mode {index} {name}[{column}]", maximum=tolerance)
        cutoffs = item.get("both_sparsification_stages")
        if not isinstance(cutoffs, dict) or set(cutoffs) != {"global", "plane"}:
            raise ValueError(f"same-live mode {index} lacks both existing sparsification stages")
        for stage, record in cutoffs.items():
            components = record.get("components") if isinstance(record, dict) else None
            if not isinstance(components, list) or len(components) != 2:
                raise ValueError(f"same-live mode {index} {stage} component cutoffs are incomplete")
            for component in components:
                if (not isinstance(component.get("raw_nonzero"), int)
                        or not isinstance(component.get("retained"), int)
                        or component["raw_nonzero"] < component["retained"]
                        or component["retained"] < 0):
                    raise ValueError(f"same-live mode {index} cutoff cardinality is invalid")
                finite_number(component.get("cutoff"), f"mode {index} {stage} cutoff", minimum=1e-30)
            finite_number(record.get("combined_C_cutoff"), f"mode {index} {stage} combined C cutoff", minimum=1e-30)
            finite_number(record.get("combined_D_cutoff"), f"mode {index} {stage} combined D cutoff", minimum=1e-30)

    for field in ("raw_vs_centered_action_defect", "new_stored_vs_raw_action_defect",
                  "physical_FE_RHS_literal_raw_defect"):
        finite_number(receipt.get(field), field, maximum=tolerance)
    for field in ("incident_transform_gate_ratio", "nonzero_port_rhs_transform_gate_ratio"):
        finite_number(receipt.get(field), field, maximum=1.0)
    output_gates = receipt["output_component_gates"]
    if [item.get("arbitrary_state_column") for item in output_gates] != list(range(5)):
        raise ValueError("same-live output-component columns must be all five ordered states")
    for output in output_gates:
        if (output.get("status") != "representable_global_output"
                or output.get("global_output_component_consistency_checked") is not True
                or output.get("official_results") is not False):
            raise ValueError("same-live output conversion component did not pass")
        checks = output.get("global_output_component_checks")
        if not isinstance(checks, list) or len(checks) != 532:
            raise ValueError("same-live output conversion is missing its complete per-mode ledger")
        for index, check in enumerate(checks):
            if check.get("mode_index") != index or check.get("global_field_finite") is not True:
                raise ValueError("same-live output conversion mode order/finite-field gate failed")
            finite_number(check.get("outgoing_roundtrip_relative_defect"),
                          f"output column {output['arbitrary_state_column']} mode {index} roundtrip",
                          maximum=tolerance)
            finite_number(check.get("outgoing_power_operation_scaled_defect"),
                          f"output column {output['arbitrary_state_column']} mode {index} power",
                          maximum=tolerance)
        zeroed = {}
        for item in output.get("analytic_zero_power_checks", []):
            index = item.get("mode_index")
            certificate = item.get("certificate", {})
            if (not isinstance(index, int) or index in zeroed
                    or certificate.get("plane", {}).get("proved") is not True
                    or certificate.get("global", {}).get("proved") is not True):
                raise ValueError("same-live analytic zero-power certificate is incomplete")
            zeroed[index] = certificate
        positive_to_zero = {check["mode_index"] for check in checks
                            if check.get("positive_to_zero_global_power") is True}
        if positive_to_zero != set(zeroed):
            raise ValueError("same-live analytic zero-power certificates do not exactly match zeroed modes")
        for check in checks:
            if check.get("positive_to_zero_global_power") is True and check["mode_index"] not in zeroed:
                raise ValueError("same-live positive-to-zero global power lacks its analytic zero certificate")


def shared_discrete_contract(identity: Mapping[str, Any], receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Return the exact carrier/profile identity inherited by the p6 worker."""
    return {
        "schema": "task40extra.fresh-c1-p6-shared-discrete-contract.v1",
        "physical_generator_manifest_sha256": identity["physical_generator_manifest_sha256"],
        "assembly_mode_manifest_sha256": identity["assembly_mode_manifest_sha256"],
        "assembly_context_sha256": identity["assembly_context_sha256"],
        "carrier_numeric_sha256": identity["carrier_numeric_sha256"],
        "mode_count": identity["mode_count"],
        "ordered_mode_keys": [list(key) for key in identity["ordered_mode_keys"]],
        "degree": receipt["degree"],
        "fresh_fixture_c1": receipt["fresh_fixture_c1"],
        "literal532_live_qualification_status": receipt["status"],
        "qualification_source_sha256": receipt["qualification_source_sha256"],
    }


def require_live_carrier_unchanged(bundle: Mapping[str, Any], expected_carrier: Any,
                                   expected_identity: Mapping[str, Any], checkpoint: Callable) -> dict[str, Any]:
    carrier = bundle["dtn_action"].carrier
    actual = carrier_numeric_identity(carrier)
    if carrier is not expected_carrier or actual != dict(expected_identity):
        checkpoint("same_live_carrier_mutation", {
            "status": "failed", "same_object": carrier is expected_carrier,
            "expected": dict(expected_identity), "actual": actual,
        })
        raise RuntimeError("component worker replaced or changed its qualified live carrier")
    checkpoint("same_live_carrier_unchanged", {"status": "passed", "identity": actual})
    return actual


def qualify_live_identity(bundle: Mapping[str, Any], *, record_path: str | Path,
                          allocation_gate: Callable, checkpoint: Callable) -> dict[str, Any]:
    """Run literal532 qualification and bind its durable receipt to this bundle."""
    if not callable(allocation_gate) or not callable(checkpoint):
        raise TypeError("same-live qualification requires allocation/checkpoint callbacks")
    carrier = bundle["dtn_action"].carrier
    before = carrier_numeric_identity(carrier)
    runtime_profile = bundle.get("runtime_profile", NATIVE_LINUX_PROFILE)
    profile = validate_fresh_c1_bundle_profile(bundle)
    if (profile["degree"] != 6 or profile["fresh_fixture_c1"] is not True
            or bundle.get("dtn_phase_gauge") != BOUNDARY_PLANE
            or before["physical_generator_manifest_sha256"]
            != profile["physical_generator_manifest_sha256"]
            or before["mode_count"] != 532):
        raise ValueError("same-live qualification accepts only the fresh same80 p6 boundary-plane bundle")
    from .fullspace_dtn_action import build_dynamic_mode_inventory
    expected_modes, _rows, expected_physical = build_dynamic_mode_inventory(bundle["cfg"])
    expected_keys = tuple((i, mode.side, mode.m, mode.n, mode.polarization)
                          for i, mode in enumerate(expected_modes))
    if (expected_physical != profile["physical_generator_manifest_sha256"]
            or tuple(before["ordered_mode_keys"]) != expected_keys):
        raise ValueError("live carrier differs from an independently regenerated ordered literal532 inventory")
    checkpoint("same_live_component_before_qualification", {
        "identity": before, "profile": profile,
        "fresh_c1_live_qualification_required": True,
        "PDE_solved": False, "official_results": False,
    })
    allocation_gate("same_live_literal532_oracle", {
        "matrix_payload_bytes": 16 << 20,
        "workspace_bytes": 128 << 20,
        "allocation_semantics": "additional objects to current whole-process-tree RSS",
        "named_small_oracle_allowance_not_peak_bound": True,
        "mode_count": 532, "degree": 6,
        "global_p6_matrix_count": 0, "global_p6_factor_count": 0,
        "PDE_solved": False,
    })
    path = Path(record_path)
    receipt = qualify_fresh_c1_p6_boundary_plane_bundle(
        bundle, record_path=path, expected_physical_manifest=expected_physical,
        expected_ordered_keys=expected_keys,
    )
    after = require_live_carrier_unchanged(bundle, carrier, before, checkpoint)
    validate_live_receipt(receipt, identity=before, runtime_profile=runtime_profile)
    stored = json.loads(path.read_text())
    if stored != receipt:
        # The writer canonicalizes tuples/NumPy scalars; compare that durable
        # representation with a JSON round-trip of the in-memory packet.
        receipt = stored
        validate_live_receipt(receipt, identity=before, runtime_profile=runtime_profile)
    checkpoint("same_live_component_pass_before_worker", {
        "status": receipt["status"], "identity": before, "after_identity": after,
        "receipt_path": str(path), "receipt_sha256": file_sha256(path),
        "receipt_schema": receipt["schema"], "literal_mode_count": 532,
        "fresh_fixture_c1": True, "PDE_solved": False, "official_results": False,
    })
    return {
        "receipt": receipt,
        "identity": before,
        "carrier": carrier,
        "shared_discrete_contract": shared_discrete_contract(before, receipt),
        "receipt_path": str(path),
        "receipt_sha256": file_sha256(path),
        "live_contract_source_sha256": file_sha256(__file__),
    }


__all__ = ("PHYSICAL_GENERATOR_SHA256", "file_sha256", "validate_live_receipt",
           "shared_discrete_contract", "require_live_carrier_unchanged", "qualify_live_identity")
