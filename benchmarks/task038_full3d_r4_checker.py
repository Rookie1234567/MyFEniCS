"""Read-only checker for compact Candidate-A/C R4 records.

This module reads canonical packet manifests and raw ledger fields only.  It
does not import the R4 worker, a production solver, PETSc, or MPI.  The
worker's status and scalar summaries are never used as a gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

import numpy as np

from benchmarks.canonical_vector_artifacts import (
    compare_canonical_packets,
    read_canonical_manifest,
    read_canonical_packet_shards,
)


R4_SCHEMA = "task038.full3d.iterative.r4.candidate-a-record.v1"
R4_C_SCHEMA = "task038.full3d.iterative.r4.candidate-c-record.v1"
R4_C_TRANSMISSION = "fixed_second_order_local_impedance_v1"
R4_C_WEAK_FORM = "per_facet_broken_tangential_derivative_action"
R4_SOURCE_NAMES = (
    "physical_rhs",
    "gradient",
    "curl",
    "checkerboard",
    "r3_qualified_long_tail",
)
R4_GATE_TOLERANCES = {
    "action": 1.0e-11,
    "repeat": 1.0e-12,
    "mpi_identity": 1.0e-12,
}
R4_CONTRACTION_LIMITS = {
    "physical_rhs": 0.60,
    "r3_qualified_long_tail": 0.70,
    "checkerboard": 0.75,
    "gradient": 0.90,
    "curl": 0.90,
}
R4_NORM_DEFINITION = "canonical full_fe_dual coefficient L2"
R4_SOURCE_GENERATION_FORMULAS = {
    "physical_rhs": "current_dtn_compose_physical_rhs(base_incident_traction,frozen_mode_amplitudes)",
    "gradient": "fixed_gradient_of_sin_product_then_current_A",
    "curl": "curl_of_A=(0,0,sin_x*sin_y*sin_z)_then_current_A",
    "checkerboard": "fixed_8_cycle_checkerboard_then_current_A",
    "r3_qualified_long_tail": "R3_canonical_full_fe_dual_reconstruct_no_empirical_scaling",
}
EXPECTED_TEMPLATE_SHA256 = "819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41"
EXPECTED_RESOLVED_SHA256 = "78dc49b3a7ae212dec6374fde09eaaa231c131ce64790202da062b3ca2b09aad"
EXPECTED_MODE_MANIFEST_SHA256 = "dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2"
EXPECTED_K0 = 2.0 * np.pi / 13.5
R3_LONG_TAIL_MANIFEST_SHA256 = "62c7824e1032b1a14078d158b0e403b9087dc862bf00386fdce08535e4d76dce"
R3_LONG_TAIL_SOURCE_SHA = "2c8fca90c7300b85b30021081868b699c0b306d2"
R3_LONG_TAIL_SOURCE_NAME = "CURRENT_RECOMPUTED_RESIDUAL_AT_HISTORICAL_W5_STATE"
WATCHDOG_RAW_SCHEMA = "task038.t5.external-process-tree-raw.v1"
WATCHDOG_COMPACT_SCHEMA = "task038.t5.external-process-tree-compact.v1"
WATCHDOG_PROCESS_TREE_CEILING_BYTES = 6 * 1024**3
R4_PROCESS_TREE_CEILING_BYTES = 6_000_000_000
WATCHDOG_HARD_STOP_BYTES = 12 * 1024**3


def _record_candidate(record: Mapping[str, Any]) -> str | None:
    schema = record.get("schema")
    if schema == R4_SCHEMA:
        return "A"
    if schema == R4_C_SCHEMA:
        return "C"
    return None


def _packets(raw_dir: Path, descriptor: Mapping[str, Any]) -> tuple[tuple[Any, ...], ...]:
    manifest_path = raw_dir / str(descriptor["manifest_relative_path"])
    manifest = read_canonical_manifest(
        manifest_path,
        str(descriptor["manifest_sha256"]),
    )
    if manifest.get("role") != descriptor.get("role"):
        raise ValueError("canonical role differs between record and manifest")
    shards = tuple(
        manifest_path.parent / item["filename"]
        for item in manifest["per_rank_shards"]
    )
    packets = read_canonical_packet_shards(
        shards,
        tuple(item["file_sha256"] for item in manifest["per_rank_shards"]),
    )
    if len(packets) != int(descriptor["packet_count"]):
        raise ValueError("canonical packet count does not match record")
    if int(descriptor["duplicate_count"]) != int(
        manifest["summed_local_duplicate_count"]
    ):
        raise ValueError("canonical duplicate count does not match record")
    if not bool(descriptor["finite"]):
        raise ValueError("record marks a non-finite canonical vector")
    if not all(np.isfinite(complex(value)) for _key, value in packets):
        raise ValueError("canonical packet contains a non-finite value")
    return packets


def _relative_difference(
    left: Iterable[tuple[tuple[Any, ...], complex]],
    right: Iterable[tuple[tuple[Any, ...], complex]],
    tolerance: float,
) -> dict[str, Any]:
    result = compare_canonical_packets(left, right, relative_tolerance=tolerance)
    # compare_canonical_packets uses the right/reference norm.  Keep that
    # convention visible in the compact checker output.
    result["reference_norm_side"] = "right"
    return result


def _subtract(
    left: Mapping[tuple[Any, ...], complex],
    right: Mapping[tuple[Any, ...], complex],
) -> tuple[tuple[tuple[Any, ...], complex], ...]:
    if set(left) != set(right):
        raise ValueError("canonical arithmetic requires identical key sets")
    return tuple((key, left[key] - right[key]) for key in sorted(left, key=repr))


def _packet_map(packets: Iterable[tuple[tuple[Any, ...], complex]]) -> dict[tuple[Any, ...], complex]:
    values: dict[tuple[Any, ...], complex] = {}
    for key, value in packets:
        if key in values:
            raise ValueError("canonical packet duplicate encountered")
        values[key] = complex(value)
    return values


def _is_hex(value: Any, length: int) -> bool:
    return isinstance(value, str) and re.fullmatch(rf"[0-9a-f]{{{length}}}", value) is not None


def _command_option_value(command: list[str], option: str) -> str | None:
    for index, token in enumerate(command):
        if token == option and index + 1 < len(command):
            return command[index + 1]
        if token.startswith(option + "="):
            return token.split("=", 1)[1]
    return None


def _check_source_identity(record: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    identity = record.get("source_identity")
    if not isinstance(identity, Mapping):
        return ["source_identity is missing"]
    expected = identity.get("expected_sha")
    start = identity.get("start")
    end = identity.get("end")
    if not _is_hex(expected, 40):
        errors.append("source_identity.expected_sha is not lowercase 40-hex")
    for label, value in (("start", start), ("end", end)):
        if not isinstance(value, Mapping) or not _is_hex(value.get("commit_sha"), 40):
            errors.append(f"source_identity.{label}.commit_sha is invalid")
        elif value.get("tracked_status") != "":
            errors.append(f"source_identity.{label} is not clean")
    if isinstance(start, Mapping) and isinstance(end, Mapping) and expected:
        if start.get("commit_sha") != expected or end.get("commit_sha") != expected:
            errors.append("expected/start/end source SHA do not bind")
    return errors


def _check_input_identity(record: Mapping[str, Any]) -> list[str]:
    identity = record.get("input_identity")
    errors: list[str] = []
    if not isinstance(identity, Mapping):
        return ["input_identity is missing"]
    if identity.get("template_sha256") != EXPECTED_TEMPLATE_SHA256:
        errors.append("template SHA is not the frozen authority input")
    if identity.get("resolved_config_sha256") != EXPECTED_RESOLVED_SHA256:
        errors.append("resolved-config SHA is not the frozen authority input")
    try:
        resolved_bytes = int(identity.get("resolved_config_bytes", -1))
    except (TypeError, ValueError):
        resolved_bytes = -1
    if resolved_bytes != 4076:
        errors.append("resolved-config byte count is not frozen")
    try:
        mode_count = int(record.get("mode_count", -1))
    except (TypeError, ValueError):
        mode_count = -1
    if mode_count != 80:
        errors.append("dynamic mode inventory count is not the frozen 80-mode benchmark")
    if record.get("mode_manifest_sha256") != EXPECTED_MODE_MANIFEST_SHA256:
        errors.append("dynamic mode manifest identity is not frozen")
    if record.get("degree") != 6:
        errors.append("formal degree is not frozen at 6")
    try:
        mesh_target = float(record.get("mesh_target_nm", np.nan))
    except (TypeError, ValueError):
        mesh_target = np.nan
    if not np.isfinite(mesh_target) or mesh_target != 10.0:
        errors.append("formal mesh target is not frozen at 10.0 nm")
    if record.get("profile") != "full3d_scalable_v1":
        errors.append("formal profile is not full3d_scalable_v1")
    if record.get("mpi_size") not in (1, 2):
        errors.append("formal MPI size is not one of the qualified sizes")
    return errors


def _check_mode_manifest(record: Mapping[str, Any], raw_dir: Path) -> list[str]:
    descriptor = record.get("mode_manifest")
    if not isinstance(descriptor, Mapping):
        return ["mode_manifest descriptor is missing"]
    path = raw_dir / str(descriptor.get("relative_path", ""))
    if not path.is_file():
        return ["mode_manifest raw artifact is missing"]
    payload = path.read_bytes()
    import hashlib

    errors: list[str] = []
    if len(payload) != int(descriptor.get("bytes", -1)):
        errors.append("mode_manifest byte count does not match")
    if hashlib.sha256(payload).hexdigest() != descriptor.get("sha256"):
        errors.append("mode_manifest descriptor hash does not match")
    if descriptor.get("sha256") != EXPECTED_MODE_MANIFEST_SHA256:
        errors.append("mode_manifest is not the frozen ordered inventory")
    if record.get("mode_manifest_sha256") != descriptor.get("sha256"):
        errors.append("record mode_manifest_sha256 is not bound to raw bytes")
    return errors


def _check_source_binding(record: Mapping[str, Any]) -> list[str]:
    source_name = record.get("source_name")
    source = record.get("source")
    errors: list[str] = []
    if not isinstance(source, Mapping) or source.get("name") != source_name:
        return ["source binding name is missing or inconsistent"]
    if record.get("norm_definition") != R4_NORM_DEFINITION:
        errors.append("record norm definition is not canonical full_fe_dual coefficient L2")
    if source.get("norm_definition") != R4_NORM_DEFINITION:
        errors.append("source norm definition is not canonical full_fe_dual coefficient L2")
    if source.get("generation_formula") != R4_SOURCE_GENERATION_FORMULAS.get(source_name):
        errors.append("source generation formula is not the frozen construction")
    if source.get("empirical_scaling") is not False:
        errors.append("source empirical_scaling is not explicitly false")
    source_generation = record.get("source_generation")
    expected_apply_count = 1 if source_name in {"gradient", "curl", "checkerboard"} else 0
    if not isinstance(source_generation, Mapping):
        errors.append("source_generation facts are missing")
    else:
        if source_generation.get("generation_formula") != R4_SOURCE_GENERATION_FORMULAS.get(source_name):
            errors.append("source_generation formula is not bound")
        if source_generation.get("empirical_scaling") is not False:
            errors.append("source_generation empirical_scaling is not false")
        if source_generation.get("physical_action_apply_count") != expected_apply_count:
            errors.append("source-generation physical apply count is not separated from sweep updates")
    if source_name == "r3_qualified_long_tail":
        if source.get("generation") != R3_LONG_TAIL_SOURCE_NAME:
            errors.append("long-tail source generation name is not bound")
        if source.get("long_tail_source_sha") != R3_LONG_TAIL_SOURCE_SHA:
            errors.append("long-tail source SHA is not bound")
        if source.get("long_tail_manifest_sha256") != R3_LONG_TAIL_MANIFEST_SHA256:
            errors.append("long-tail manifest SHA is not bound")
    elif source.get("generation") not in {
        "current_physical_rhs",
        "fixed_analytic_primal_then_current_A",
    }:
        errors.append("source generation is not a frozen current construction")
    return errors


def _complex_pair(value: Any) -> complex | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    if any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in value):
        return None
    result = complex(float(value[0]), float(value[1]))
    return result if np.isfinite(result.real) and np.isfinite(result.imag) else None


def _canonical_class_key(value: Any) -> tuple[float, ...] | None:
    if not isinstance(value, list) or len(value) != 8:
        return None
    if any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in value):
        return None
    values = tuple(float(item) for item in value)
    return values if all(np.isfinite(item) for item in values) else None


def _check_candidate_c_audit(record: Mapping[str, Any]) -> list[str]:
    """Recompute Candidate-C's frozen coefficients from its compact facts."""

    errors: list[str] = []
    if _record_candidate(record) != "C" or record.get("candidate") != "C":
        errors.append("Candidate-C record identity is missing")
    identity = record.get("candidate_identity")
    if not isinstance(identity, Mapping):
        return errors + ["Candidate-C identity is missing"]
    for key, expected in (
        ("candidate", "C"),
        ("schema", R4_C_SCHEMA),
        ("transmission", R4_C_TRANSMISSION),
    ):
        if identity.get(key) != expected:
            errors.append(f"candidate_identity.{key} is not frozen for Candidate C")
    k0_value = identity.get("k0")
    try:
        k0 = float(k0_value)
    except (TypeError, ValueError):
        k0 = float("nan")
    if not np.isfinite(k0) or not np.isclose(k0, EXPECTED_K0, rtol=0.0, atol=1.0e-14):
        errors.append("candidate_identity.k0 does not match wavelength_nm=13.5")

    transmission = record.get("transmission_audit")
    candidate_audit = record.get("candidate_audit")
    if not isinstance(transmission, Mapping):
        errors.append("Candidate-C transmission_audit is missing")
        return errors
    if not isinstance(candidate_audit, Mapping):
        errors.append("Candidate-C candidate_audit is missing")
    elif candidate_audit.get("transmission_audit") != transmission:
        errors.append("Candidate-C sweep and transmission audits differ")

    expected_fields = {
        "schema": "task038.fullspace-fixed-second-order-impedance.v1",
        "candidate": "C",
        "transmission": R4_C_TRANSMISSION,
        "operator_name": "fixed_second_order_local_impedance",
        "exact_local_dtn": False,
        "weak_form": R4_C_WEAK_FORM,
        "weak_form_support": "interface_facet_dS_material_pair_tags_only",
        "derivative_semantics": "per_facet_broken_tangential_derivative",
        "forward_neighbor": "upper",
        "backward_neighbor": "lower",
        "parameters_frozen_before_rho": True,
        "spectral_threshold": "not_used",
        "local_patch_range": "not_used",
        "local_krylov_steps": 0,
        "factor_count": 0,
        "per_cell_retained_tensor_count": 0,
        "global_aij_materialized": False,
        "global_schur_materialized": False,
        "dense_interface_matrix_materialized": False,
        "growing_slab_factor_materialized": False,
        "numeric_allgather": False,
        "phase_application": "finalized_floquet_mpc_once",
        "slave_row_identity": False,
    }
    for key, expected in expected_fields.items():
        if transmission.get(key) != expected:
            errors.append(f"transmission_audit.{key} is not independently qualified")

    action_audits = transmission.get("action_audits")
    if not isinstance(action_audits, Mapping) or set(action_audits) != {"forward", "backward"}:
        errors.append("Candidate-C action audits are not exactly forward/backward")
    else:
        action_false_fields = (
            "global_matrix_materialized",
            "global_constraint_matrix_materialized",
            "global_condensed_schur_materialized",
            "cell_schur_matrix_materialized",
            "slab_matrix_materialized",
            "numeric_allgather",
        )
        for direction, action_audit in action_audits.items():
            if not isinstance(action_audit, Mapping):
                errors.append(f"Candidate-C {direction} action audit is not an object")
                continue
            if action_audit.get("slave_row_identity") is not False:
                errors.append(f"Candidate-C {direction} action enables slave identity")
            if action_audit.get("phase_application") != "finalized_floquet_mpc_once":
                errors.append(f"Candidate-C {direction} action phase audit is missing")
            for field in action_false_fields:
                if action_audit.get(field) is not False:
                    errors.append(f"Candidate-C {direction} action {field} is not false")
            if action_audit.get("factor_count") != 0:
                errors.append(f"Candidate-C {direction} action factor_count is not zero")

    manifest = transmission.get("class_manifest")
    try:
        class_count = int(transmission.get("class_count", -1))
    except (TypeError, ValueError):
        class_count = -1
    if class_count != 2 or not isinstance(manifest, list) or len(manifest) != 4:
        errors.append("Candidate-C manifest is not exactly two classes by two directions")
        manifest = manifest if isinstance(manifest, list) else []
    class_keys: set[tuple[float, ...]] = set()
    classifications = {
        row.get("classification") for row in manifest if isinstance(row, Mapping)
    }
    for row in manifest:
        if isinstance(row, Mapping):
            class_key = _canonical_class_key(row.get("class_key"))
            if class_key is None:
                errors.append("Candidate-C class_key is not a finite production 8-number list")
            else:
                class_keys.add(class_key)
    if len(class_keys) != 2:
        errors.append("Candidate-C manifest does not contain two material-pair classes")
    if classifications != {"homogeneous", "nonhomogeneous"}:
        errors.append("Candidate-C manifest does not record mixed homogeneous classes")
    seen: set[tuple[tuple[float, ...], Any]] = set()
    for row in manifest:
        if not isinstance(row, Mapping):
            errors.append("Candidate-C manifest row is not an object")
            continue
        class_key = _canonical_class_key(row.get("class_key"))
        if class_key is not None:
            key = (class_key, row.get("direction"))
            if key in seen:
                errors.append("Candidate-C manifest contains duplicate class/direction rows")
            seen.add(key)
        direction = row.get("direction")
        expected_side = "upper" if direction == "forward" else "lower" if direction == "backward" else None
        if expected_side is None or row.get("neighbor_side") != expected_side:
            errors.append("Candidate-C manifest direction/neighbor side is inconsistent")
        if not isinstance(row.get("lower_material_tag"), int) or isinstance(row.get("lower_material_tag"), bool):
            errors.append("Candidate-C lower material tag is not an integer")
        if not isinstance(row.get("upper_material_tag"), int) or isinstance(row.get("upper_material_tag"), bool):
            errors.append("Candidate-C upper material tag is not an integer")
        neighbor_n = _complex_pair(row.get("neighbor_n"))
        if neighbor_n is None or neighbor_n == 0j or not np.isfinite(k0):
            errors.append("Candidate-C neighbor refractive index is invalid")
            continue
        expected_coefficients = (
            -1j * k0 * neighbor_n,
            1j * k0 / (2.0 * neighbor_n),
            -1j * k0 / (2.0 * neighbor_n),
            -1j * k0 / neighbor_n,
        )
        for field, expected in zip(
            ("y0", "a_s", "a_p", "d"), expected_coefficients, strict=True
        ):
            observed = _complex_pair(row.get(field))
            if observed is None or not np.isclose(
                observed, expected, rtol=0.0, atol=1.0e-13
            ):
                errors.append(f"Candidate-C manifest coefficient {field} is not formula-bound")

    manifest_bytes = json.dumps(
        manifest, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    if transmission.get("class_manifest_serialized_bytes") != len(manifest_bytes):
        errors.append("Candidate-C manifest byte count is not raw-derived")
    if transmission.get("class_manifest_sha256") != hashlib.sha256(manifest_bytes).hexdigest():
        errors.append("Candidate-C manifest SHA is not raw-derived")

    payload = transmission.get("retained_numeric_payload")
    expected_count = 2 * 2 * 3
    if not isinstance(payload, Mapping):
        errors.append("Candidate-C retained numeric payload is missing")
    else:
        if payload.get("fem_constant_complex_scalar_count") != expected_count:
            errors.append("Candidate-C constant count is not two classes by two directions")
        if payload.get("fem_constant_complex_scalar_bytes") != 16:
            errors.append("Candidate-C scalar storage is not complex128")
        if payload.get("fem_constant_values_bytes") != 192:
            errors.append("Candidate-C retained scalar payload is not the 192-byte formula")
        if payload.get("a_p_storage") != "derived_from_a_s_plus_d_not_retained_as_constant":
            errors.append("Candidate-C a_p retention policy is not explicit")
        if payload.get("scaling") != "O(material_pair_class_count)":
            errors.append("Candidate-C payload scaling is not class-bounded")
    if transmission.get("retained_numeric_payload_bytes") != 192:
        errors.append("Candidate-C retained numeric payload bytes are not 192")
    if transmission.get("retained_numeric_payload_scaling") != "O(material_pair_class_count)":
        errors.append("Candidate-C retained payload scaling is not class-bounded")
    return errors


def _check_watchdog(
    raw_path: Path | None,
    compact_path: Path | None,
    record_path: Path,
    record: Mapping[str, Any],
) -> tuple[str, dict[str, Any], list[str]]:
    """Recompute the repository T5 raw/compact process-tree contract."""

    if raw_path is None and compact_path is None:
        return "not_run", {}, []
    if raw_path is None or compact_path is None:
        return "fail", {}, ["watchdog requires both T5 raw and compact reports"]
    errors: list[str] = []
    if not raw_path.is_file() or not compact_path.is_file():
        return "fail", {}, ["T5 watchdog raw or compact report is missing"]
    try:
        raw_payload = raw_path.read_bytes()
        compact_payload = compact_path.read_bytes()
        raw = json.loads(raw_payload)
        compact = json.loads(compact_payload)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return "fail", {}, [f"T5 watchdog report is unreadable: {exc}"]

    raw_sha = hashlib.sha256(raw_payload).hexdigest()
    compact_sha = hashlib.sha256(compact_payload).hexdigest()
    if raw.get("schema") != WATCHDOG_RAW_SCHEMA:
        errors.append("watchdog raw schema is not task038.t5 raw")
    if compact.get("schema") != WATCHDOG_COMPACT_SCHEMA:
        errors.append("watchdog compact schema is not task038.t5 compact")
    if compact.get("raw_report_sha256") != raw_sha:
        errors.append("watchdog compact does not bind raw SHA")
    if compact.get("status") != "measured_pass":
        errors.append("watchdog compact status is not measured_pass")
    if compact.get("process_tree_memory_ceiling_bytes") != WATCHDOG_PROCESS_TREE_CEILING_BYTES:
        errors.append("watchdog process-tree ceiling is not 6 GiB")
    if compact.get("hard_stop_memory_bytes") != WATCHDOG_HARD_STOP_BYTES:
        errors.append("watchdog hard stop is not 12 GiB")
    if compact.get("swap_required_bytes") != 0:
        errors.append("watchdog swap contract is not zero")
    command = raw.get("command")
    expected_sha = record.get("source_identity", {}).get("expected_sha")
    mpi_size = record.get("mpi_size")
    if not isinstance(command, list) or not all(isinstance(item, str) for item in command):
        errors.append("watchdog command is missing or malformed")
        command = []
    required_options = {
        "--record": str(record_path.resolve()),
        "--source": record.get("source_name"),
        "--expected-source-sha": expected_sha,
        "--degree": "6",
        "--expected-mpi-size": str(mpi_size),
    }
    if _record_candidate(record) == "C":
        required_options["--candidate"] = "C"
    for option, expected in required_options.items():
        if _command_option_value(command, option) != expected:
            errors.append(f"watchdog command is not bound for {option}")
    mesh_option = _command_option_value(command, "--mesh-target")
    try:
        mesh_matches = float(mesh_option) == 10.0
    except (TypeError, ValueError):
        mesh_matches = False
    if not mesh_matches:
        errors.append("watchdog command is not bound for --mesh-target=10.0")

    samples = raw.get("samples")
    if not isinstance(samples, list) or not samples:
        errors.append("watchdog raw samples are missing or empty")
        samples = []
    rss_values: list[int] = []
    tree_swap_values: list[int] = []
    cgroup_swap_values: list[int] = []
    authority_values: list[int] = []
    all_readable = True
    for sample in samples:
        if not isinstance(sample, Mapping):
            errors.append("watchdog sample is not an object")
            continue
        tree = sample.get("process_tree")
        cgroup = sample.get("job_cgroup")
        if not isinstance(tree, Mapping) or not isinstance(cgroup, Mapping):
            errors.append("watchdog sample lacks process-tree/cgroup fields")
            continue
        numeric = (
            tree.get("rss_bytes"),
            tree.get("swap_bytes"),
            sample.get("memory_authority_bytes"),
        )
        if any(isinstance(value, bool) or not isinstance(value, int) for value in numeric):
            errors.append("watchdog sample has invalid resource integers")
            continue
        rss_values.append(int(tree["rss_bytes"]))
        tree_swap_values.append(int(tree["swap_bytes"]))
        authority_values.append(int(sample["memory_authority_bytes"]))
        all_readable = bool(
            all_readable
            and tree.get("all_status_readable") is True
            and sample.get("job_no_swap") is True
        )
        if cgroup.get("dedicated_job_cgroup") is True:
            swap_value = cgroup.get("swap_current_bytes")
            if isinstance(swap_value, bool) or not isinstance(swap_value, int):
                errors.append("dedicated cgroup swap is unreadable or invalid")
            else:
                cgroup_swap_values.append(int(swap_value))

    observed = {
        "process_tree_peak_rss_bytes": max(rss_values, default=0),
        "process_tree_peak_swap_bytes": max(tree_swap_values, default=0),
        "dedicated_cgroup_peak_swap_bytes": max(cgroup_swap_values, default=0),
        "memory_authority_peak_bytes": max(authority_values, default=0),
        "sample_count": len(samples),
        "all_status_readable": bool(samples) and all_readable,
    }
    for key, value in observed.items():
        if compact.get(key) != value:
            errors.append(f"watchdog compact field is not raw-derived: {key}")

    returncode = raw.get("returncode")
    termination = raw.get("termination")
    if compact.get("returncode") != returncode or returncode != 0:
        errors.append("watchdog worker return code is not zero or not bound")
    if raw.get("stop_reason") is not None or compact.get("stop_reason") is not None:
        errors.append("watchdog recorded a stop reason")
    if compact.get("termination") != termination:
        errors.append("watchdog compact termination is not raw-derived")
    if not isinstance(termination, Mapping) or termination.get("process_group_exited") is not True:
        errors.append("watchdog process group did not close")
    if isinstance(termination, Mapping) and termination.get("sigkill_required") is not False:
        errors.append("watchdog termination was not a normal non-SIGKILL exit")
    if not observed["all_status_readable"]:
        errors.append("watchdog process-tree status was not fully readable")
    if observed["process_tree_peak_rss_bytes"] >= R4_PROCESS_TREE_CEILING_BYTES:
        errors.append("process-tree peak RSS is not below decimal 6,000,000,000 B")
    if observed["memory_authority_peak_bytes"] >= WATCHDOG_HARD_STOP_BYTES:
        errors.append("memory-authority peak reached the 12 GiB hard stop")
    if (
        observed["process_tree_peak_swap_bytes"] != 0
        or observed["dedicated_cgroup_peak_swap_bytes"] != 0
    ):
        errors.append("watchdog observed nonzero swap")
    facts = {
        **observed,
        "returncode": returncode,
        "termination": termination,
        "raw_path": str(raw_path.resolve()),
        "compact_path": str(compact_path.resolve()),
        "raw_sha256": raw_sha,
        "compact_sha256": compact_sha,
    }
    return "pass" if not errors else "fail", facts, errors


def _check_ledger(record: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    candidate = _record_candidate(record)
    audit = record.get("candidate_audit")
    if not isinstance(audit, Mapping):
        return ["candidate_audit is missing"]
    expected = {
        "profile": "full3d_scalable_v1",
        "slab_count": 2,
        "forward_order": [0, 1],
        "backward_order": [1, 0],
        "transmission": (
            R4_C_TRANSMISSION if candidate == "C" else "first_order_impedance_robin_v1"
        ),
        "transmission_q": (
            "fixed y0=-i*k0*n_neighbor" if candidate == "C" else "-i*k0*n_side"
        ),
        "local_ksp_count": 2,
        "local_operator_type": "PETSc.MatShell",
        "global_ksp_created": False,
        "local_ksp_restart": 8,
        "local_ksp_max_it": 8,
        "expected_diverged_its": -3,
        "pou": "inverse_owner_multiplicity",
        "parameters_frozen_before_rho": True,
    }
    for key, value in expected.items():
        if audit.get(key) != value:
            errors.append(f"candidate_audit.{key} does not match frozen contract")
    sweep = record.get("sweep")
    if not isinstance(sweep, Mapping):
        return errors + ["sweep is missing"]
    ledger = sweep.get("ledger")
    expected_steps = [
        ("forward", 0, 1),
        ("forward", 1, None),
        ("backward", 1, 0),
        ("backward", 0, None),
    ]
    if not isinstance(ledger, list) or len(ledger) != len(expected_steps) or [
        (row.get("direction"), row.get("slab"), row.get("neighbor_slab"))
        for row in ledger
    ] != expected_steps:
        errors.append("forward/backward ledger order is not closed")
    for row, (_direction, _slab, neighbor_slab) in zip(
        ledger if isinstance(ledger, list) else (), expected_steps, strict=False
    ):
        solve = row.get("solve", {}) if isinstance(row, Mapping) else {}
        try:
            fixed_max_iterations = int(solve.get("fixed_max_iterations", -1))
            reason = int(solve.get("reason", 0))
        except (TypeError, ValueError):
            fixed_max_iterations = -1
            reason = 0
        if fixed_max_iterations != 8:
            errors.append("local solve is not fixed at eight iterations")
        if reason < 0 and reason != -3:
            errors.append("local KSP has an unexpected divergence reason")
        if not isinstance(row, Mapping):
            continue
        for field in (
            "rhs_sha256",
            "correction_sha256",
            "action_sha256",
            "residual_sha256",
        ):
            if not _is_hex(row.get(field), 64):
                errors.append(f"ledger {field} is not hash-bound")
        if neighbor_slab is None:
            if row.get("neighbor_action_sha256") is not None or row.get("neighbor_residual_sha256") is not None:
                errors.append("terminal ledger step has unexpected neighbor packet")
            if row.get("outgoing_definition") != "updated_residual_after_A_current_c_j":
                errors.append("terminal ledger outgoing definition is not residual update")
        else:
            if not _is_hex(row.get("neighbor_action_sha256"), 64) or not _is_hex(row.get("neighbor_residual_sha256"), 64):
                errors.append("neighbor update is not hash-bound")
            if row.get("outgoing_definition") != "R_next(A_current_c_j)":
                errors.append("ledger outgoing data is not exact-action restricted residual evidence")
    actual = sweep.get("audit")
    if not isinstance(actual, Mapping):
        errors.append("sweep.audit is missing")
        return errors
    if actual.get("cell_restriction") != "owned_cells_partitioned_by_cfg.interface_z":
        errors.append("sweep does not record a real cfg.interface_z cell restriction")
    if float(actual.get("pou_max_error", np.inf)) > 1.0e-14:
        errors.append("sweep PoU audit exceeds the fixed identity tolerance")
    if actual.get("outer_boundary_slab") != {"bottom": 0, "top": 1}:
        errors.append("outer DtN side ownership is not explicit")
    if actual.get("outer_dtn_shared_action_side_restricted") is not True:
        errors.append("outer DtN side restriction was not recorded")
    if actual.get("residual_propagation") is not True:
        errors.append("sweep is not fixed residual propagation")
    try:
        recursive_error = float(actual.get("recursive_residual_closure_relative_error", np.inf))
    except (TypeError, ValueError):
        recursive_error = np.inf
    if recursive_error > 1.0e-11:
        errors.append("recursive residual is not closed against b-A_delta")
    if actual.get("exact_update_apply_count") != 5:
        errors.append("one forward/backward sweep does not contain five exact physical updates")
    if sweep.get("exact_update_apply_count_cumulative") != 10:
        errors.append("repeat run does not close ten exact physical updates")
    if actual.get("local_ksp_count") != 2:
        errors.append("sweep does not expose the two fixed local KSPs")
    if actual.get("local_operator_type") != "PETSc.MatShell":
        errors.append("local sweep operators are not MatShells")
    if actual.get("global_ksp_created") is not False:
        errors.append("sweep global_ksp_created is not explicit false")
    if "retained_slab_numeric_bytes" in actual:
        errors.append("sweep uses the obsolete retained_slab_numeric_bytes field")
    try:
        retained_support = int(actual.get("retained_support_metadata_bytes", -1))
        basis_vectors = int(actual.get("fixed_gmres_basis_vectors", -1))
        basis_bytes = int(actual.get("fixed_gmres_arnoldi_basis_derived_bytes_per_rank", -1))
    except (TypeError, ValueError):
        retained_support = basis_vectors = basis_bytes = -1
    if retained_support <= 0:
        errors.append("retained support metadata bytes are not measured")
    if basis_vectors != 18 or basis_bytes <= 0:
        errors.append("fixed GMRES workspace bound is not derived from the frozen restart")
    if actual.get("retained_support_metadata_scaling") != "O(local_owned_volume_rows)":
        errors.append("retained support metadata scaling is not explicit")
    if actual.get("fixed_gmres_workspace_scaling") != "O(fixed_restart * local_storage)":
        errors.append("fixed GMRES workspace scaling is not explicit")
    if actual.get("fixed_gmres_workspace_scope") != "Arnoldi_basis_derived_only; other_KSP_work_process_tree_measured":
        errors.append("fixed GMRES bytes are not explicitly scoped to Arnoldi basis")
    for key in (
        "global_aij_materialized",
        "global_schur_materialized",
        "dense_interface_materialized",
        "growing_slab_factor_materialized",
        "numeric_allgather",
    ):
        if actual.get(key) is not False:
            errors.append(f"sweep audit {key} is not explicit false")
    return errors


def _check_operator_audit(record: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    operator = record.get("operator_audit")
    candidate = record.get("candidate_audit")
    if not isinstance(operator, Mapping) or not isinstance(candidate, Mapping):
        return ["operator/candidate audit is missing"]
    required_false = {
        "operator_audit": (
            "global_aij_materialized",
            "global_schur_materialized",
            "ksp_created",
            "numeric_allgather",
        ),
        "candidate_audit": (
            "global_aij_materialized",
            "global_schur_materialized",
            "global_ksp_created",
            "dense_interface_materialized",
            "growing_slab_factor_materialized",
            "numeric_allgather",
        ),
    }
    for label, audit, fields in (
        ("operator_audit", operator, required_false["operator_audit"]),
        ("candidate_audit", candidate, required_false["candidate_audit"]),
    ):
        for field in fields:
            if audit.get(field) is not False:
                errors.append(f"{label}.{field} must be explicit false")
    nested = {
        "volume_action": (
            "global_matrix_materialized",
            "global_constraint_matrix_materialized",
            "global_condensed_schur_materialized",
            "cell_schur_matrix_materialized",
            "slab_matrix_materialized",
            "factor_count",
            "numeric_allgather",
            "ksp_created",
        ),
        "dtn_action": (
            "explicit_c_matrix_count",
            "explicit_d_matrix_count",
            "numeric_allgather",
        ),
    }
    for name, fields in nested.items():
        value = operator.get(name)
        if not isinstance(value, Mapping):
            errors.append(f"operator_audit.{name} is missing")
            continue
        for field in fields:
            expected = 0 if field.endswith("count") else False
            if value.get(field) != expected:
                errors.append(f"operator_audit.{name}.{field} is not explicit {expected}")
    sweep_audit = record.get("sweep", {}).get("audit", {})
    split_audits = sweep_audit.get("split_volume_action_audits") if isinstance(sweep_audit, Mapping) else None
    if not isinstance(split_audits, list) or len(split_audits) != 2:
        errors.append("two split volume action audits are missing")
    else:
        split_false_fields = (
            "global_matrix_materialized",
            "global_constraint_matrix_materialized",
            "global_condensed_schur_materialized",
            "cell_schur_matrix_materialized",
            "slab_matrix_materialized",
            "numeric_allgather",
            "ksp_created",
        )
        for index, audit in enumerate(split_audits):
            if not isinstance(audit, Mapping):
                errors.append(f"split volume audit {index} is not an object")
                continue
            if audit.get("slave_row_identity") is not False:
                errors.append(f"split volume audit {index} does not disable slave identity")
            for field in split_false_fields:
                expected = 0 if field == "factor_count" else False
                if audit.get(field) is not expected:
                    errors.append(f"split volume audit {index}.{field} is not explicit false")
            if audit.get("factor_count") != 0:
                errors.append(f"split volume audit {index}.factor_count is not zero")
    return errors


def check_record(
    record_path: Path,
    watchdog_raw_path: Path | None = None,
    watchdog_compact_path: Path | None = None,
) -> dict[str, Any]:
    record = json.loads(record_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    candidate = _record_candidate(record)
    if candidate is None:
        errors.append("record schema is unsupported")
    elif candidate == "C":
        errors.extend(_check_candidate_c_audit(record))
    elif record.get("candidate") not in (None, "A"):
        errors.append("Candidate-A record declares a different candidate")
    source_name = record.get("source_name")
    if source_name not in R4_SOURCE_NAMES:
        errors.append("source_name is not one of the frozen five sources")
    errors.extend(_check_source_identity(record))
    errors.extend(_check_input_identity(record))
    errors.extend(_check_source_binding(record))
    raw_value = record.get("raw_dir")
    if not isinstance(raw_value, str) or not raw_value:
        errors.append("raw_dir is required and must be explicit")
        raw_dir = record_path.parent
    else:
        raw_dir = Path(raw_value)
    errors.extend(_check_mode_manifest(record, raw_dir))
    artifacts = record.get("artifacts")
    packets: dict[str, tuple[tuple[Any, ...], ...]] = {}
    if not isinstance(artifacts, Mapping):
        errors.append("artifacts are missing")
    else:
        for name in ("source", "delta", "action_delta", "r_new", "repeat_r_new"):
            descriptor = artifacts.get(name)
            if not isinstance(descriptor, Mapping):
                errors.append(f"artifact {name} is missing")
                continue
            try:
                packets[name] = _packets(raw_dir, descriptor)
            except (OSError, KeyError, TypeError, ValueError) as exc:
                errors.append(f"artifact {name}: {exc}")

    arithmetic: dict[str, Any] = {}
    if all(name in packets for name in ("source", "action_delta", "r_new", "repeat_r_new")):
        try:
            source = _packet_map(packets["source"])
            action = _packet_map(packets["action_delta"])
            residual = _packet_map(packets["r_new"])
            repeat = _packet_map(packets["repeat_r_new"])
            recomputed = _subtract(source, action)
            arithmetic["r_new_recompute"] = _relative_difference(
                recomputed, tuple(residual.items()), R4_GATE_TOLERANCES["action"]
            )
            arithmetic["repeat_identity"] = _relative_difference(
                tuple(repeat.items()), tuple(residual.items()), R4_GATE_TOLERANCES["repeat"]
            )
            arithmetic["source_norm"] = float(
                np.linalg.norm(np.asarray(tuple(source.values()), dtype=np.complex128))
            )
            arithmetic["action_norm"] = float(
                np.linalg.norm(np.asarray(tuple(action.values()), dtype=np.complex128))
            )
            arithmetic["residual_norm"] = float(
                np.linalg.norm(np.asarray(tuple(residual.values()), dtype=np.complex128))
            )
            arithmetic["rho"] = float(
                arithmetic["residual_norm"] / max(arithmetic["source_norm"], np.finfo(float).tiny)
            )
            arithmetic["contraction_limit"] = R4_CONTRACTION_LIMITS.get(source_name)
            arithmetic["contraction_pass"] = bool(
                arithmetic["contraction_limit"] is not None
                and arithmetic["rho"] <= arithmetic["contraction_limit"]
            )
            arithmetic["finite"] = bool(
                all(np.isfinite(value) for value in source.values())
                and all(np.isfinite(value) for value in action.values())
                and all(np.isfinite(value) for value in residual.values())
            )
        except (TypeError, ValueError, FloatingPointError) as exc:
            errors.append(f"canonical arithmetic: {exc}")

    errors.extend(_check_ledger(record))
    errors.extend(_check_operator_audit(record))
    resource_gate, watchdog_facts, watchdog_errors = _check_watchdog(
        watchdog_raw_path,
        watchdog_compact_path,
        record_path,
        record,
    )
    errors.extend(watchdog_errors)

    numeric_pass = bool(
        not errors
        and arithmetic.get("finite") is True
        and arithmetic.get("r_new_recompute", {}).get("pass") is True
        and arithmetic.get("repeat_identity", {}).get("pass") is True
        and arithmetic.get("source_norm", 0.0) > 0.0
        and arithmetic.get("contraction_pass") is True
    )
    return {
        "schema": (
            "task038.full3d.iterative.r4.candidate-c-check.v1"
            if candidate == "C"
            else "task038.full3d.iterative.r4.candidate-a-check.v1"
        ),
        "candidate": candidate or "unknown",
        "record": str(record_path),
        "source_name": source_name,
        "numeric_pass": numeric_pass,
        "resource_gate": resource_gate,
        "watchdog": watchdog_facts,
        "arithmetic": arithmetic,
        "errors": errors,
        "status": "PASS" if numeric_pass and resource_gate == "pass" else "NOT_READY" if numeric_pass and resource_gate == "not_run" else "FAIL",
        "process_tree_not_measured": resource_gate == "not_run",
        "closure_definition": "checker recomputes r_new = b - A_delta from canonical raw packets",
    }


def check_pair(
    left_path: Path,
    right_path: Path,
    left_watchdog_raw: Path | None = None,
    left_watchdog_compact: Path | None = None,
    right_watchdog_raw: Path | None = None,
    right_watchdog_compact: Path | None = None,
) -> dict[str, Any]:
    """Compare the same source's canonical packets across two MPI records."""

    left = json.loads(left_path.read_text(encoding="utf-8"))
    right = json.loads(right_path.read_text(encoding="utf-8"))
    left_candidate = _record_candidate(left)
    right_candidate = _record_candidate(right)
    if left_candidate != right_candidate:
        return {"status": "FAIL", "errors": ["MPI pair candidates differ"]}
    if left.get("source_name") != right.get("source_name"):
        return {"status": "FAIL", "errors": ["MPI pair source names differ"]}
    if {left.get("mpi_size"), right.get("mpi_size")} != {1, 2}:
        return {"status": "FAIL", "errors": ["MPI pair is not exactly MPI1 plus MPI2"]}
    left_individual = check_record(
        left_path,
        left_watchdog_raw,
        left_watchdog_compact,
    )
    right_individual = check_record(
        right_path,
        right_watchdog_raw,
        right_watchdog_compact,
    )
    if left_individual.get("status") != "PASS" or right_individual.get("status") != "PASS":
        return {
            "status": "FAIL",
            "errors": ["individual checker must PASS before MPI pair"],
            "left_individual": left_individual,
            "right_individual": right_individual,
        }
    left_dir = Path(left["raw_dir"])
    right_dir = Path(right["raw_dir"])
    comparisons: dict[str, Any] = {}
    for name in ("source", "delta", "action_delta", "r_new", "repeat_r_new"):
        left_packets = _packets(left_dir, left["artifacts"][name])
        right_packets = _packets(right_dir, right["artifacts"][name])
        comparisons[name] = _relative_difference(
            left_packets,
            right_packets,
            R4_GATE_TOLERANCES["mpi_identity"],
        )
    passed = all(item["pass"] for item in comparisons.values())
    return {
        "schema": (
            "task038.full3d.iterative.r4.candidate-c-pair-check.v1"
            if left_candidate == "C"
            else "task038.full3d.iterative.r4.candidate-a-pair-check.v1"
        ),
        "candidate": left_candidate or "unknown",
        "status": "PASS" if passed else "FAIL",
        "comparisons": comparisons,
        "errors": [] if passed else ["one or more canonical MPI comparisons failed"],
    }


def check_aggregate(
    mpi1_records: Iterable[Path],
    mpi2_records: Iterable[Path],
    mpi1_watchdog_raws: Iterable[Path] = (),
    mpi1_watchdog_compacts: Iterable[Path] = (),
    mpi2_watchdog_raws: Iterable[Path] = (),
    mpi2_watchdog_compacts: Iterable[Path] = (),
) -> dict[str, Any]:
    """Require five records, five pairs, and raw/compact watchdog pairs."""

    left = tuple(mpi1_records)
    right = tuple(mpi2_records)
    left_raws = tuple(mpi1_watchdog_raws)
    left_compacts = tuple(mpi1_watchdog_compacts)
    right_raws = tuple(mpi2_watchdog_raws)
    right_compacts = tuple(mpi2_watchdog_compacts)
    expected = set(R4_SOURCE_NAMES)
    if len(left) != 5 or len(right) != 5:
        return {"status": "FAIL", "errors": ["aggregate requires exactly five MPI1 and five MPI2 records"]}
    if (
        len(left_raws) != 5
        or len(left_compacts) != 5
        or len(right_raws) != 5
        or len(right_compacts) != 5
    ):
        return {
            "status": "FAIL",
            "errors": ["aggregate requires five MPI1/MPI2 watchdog raw+compact pairs"],
        }
    left_payloads = [json.loads(path.read_text(encoding="utf-8")) for path in left]
    right_payloads = [json.loads(path.read_text(encoding="utf-8")) for path in right]
    candidates = {
        _record_candidate(payload)
        for payload in (*left_payloads, *right_payloads)
    }
    left_names = [json.loads(path.read_text(encoding="utf-8")).get("source_name") for path in left]
    right_names = [json.loads(path.read_text(encoding="utf-8")).get("source_name") for path in right]
    errors: list[str] = []
    if candidates != {"A"} and candidates != {"C"}:
        errors.append("aggregate mixes Candidate-A/C or has an unsupported schema")
    aggregate_candidate = next(iter(candidates)) if len(candidates) == 1 else "unknown"
    if set(left_names) != expected or set(right_names) != expected or len(set(left_names)) != 5 or len(set(right_names)) != 5:
        errors.append("aggregate source inventory is not exactly the frozen five")
    if (
        sum(json.loads(path.read_text(encoding="utf-8")).get("mpi_size") == 1 for path in left) != 5
        or sum(json.loads(path.read_text(encoding="utf-8")).get("mpi_size") == 2 for path in left) != 0
        or sum(json.loads(path.read_text(encoding="utf-8")).get("mpi_size") == 2 for path in right) != 5
        or sum(json.loads(path.read_text(encoding="utf-8")).get("mpi_size") == 1 for path in right) != 0
    ):
        errors.append("aggregate does not contain one MPI1 and one MPI2 record per source")
    individuals = {
        "mpi1": {
            name: check_record(path, raw, compact)
            for name, path, raw, compact in zip(
                left_names, left, left_raws, left_compacts, strict=True
            )
        },
        "mpi2": {
            name: check_record(path, raw, compact)
            for name, path, raw, compact in zip(
                right_names, right, right_raws, right_compacts, strict=True
            )
        },
    }
    for mpi_label, results in individuals.items():
        for name, result in results.items():
            if result.get("status") != "PASS":
                errors.append(f"{mpi_label} {name} individual check is not PASS")
    pairs: dict[str, Any] = {}
    for name in R4_SOURCE_NAMES:
        if name in individuals["mpi1"] and name in individuals["mpi2"]:
            left_path = left[left_names.index(name)]
            right_path = right[right_names.index(name)]
            pair = check_pair(
                left_path,
                right_path,
                left_raws[left_names.index(name)],
                left_compacts[left_names.index(name)],
                right_raws[right_names.index(name)],
                right_compacts[right_names.index(name)],
            )
            pairs[name] = pair
            if pair.get("status") != "PASS":
                errors.append(f"{name} MPI pair check is not PASS")
    return {
        "schema": (
            "task038.full3d.iterative.r4.candidate-c-aggregate.v1"
            if aggregate_candidate == "C"
            else "task038.full3d.iterative.r4.candidate-a-aggregate.v1"
        ),
        "candidate": aggregate_candidate,
        "status": "PASS" if not errors else "FAIL",
        "individuals": individuals,
        "pairs": pairs,
        "errors": errors,
        "required_sources": list(R4_SOURCE_NAMES),
        "resource_gate": "all_individual_watchdogs_required",
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", type=Path)
    parser.add_argument("--watchdog-raw", type=Path)
    parser.add_argument("--watchdog-compact", type=Path)
    parser.add_argument("--pair", nargs=2, type=Path)
    parser.add_argument("--pair-watchdog-raws", nargs=2, type=Path)
    parser.add_argument("--pair-watchdog-compacts", nargs=2, type=Path)
    parser.add_argument("--aggregate", nargs=10, type=Path)
    parser.add_argument("--aggregate-watchdog-raws", nargs=10, type=Path)
    parser.add_argument("--aggregate-watchdog-compacts", nargs=10, type=Path)
    parser.add_argument("--output", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    selected = sum(value is not None for value in (args.record, args.pair, args.aggregate))
    if selected != 1:
        raise SystemExit("provide exactly one of --record, --pair, or --aggregate")
    if args.record:
        result = check_record(
            args.record,
            args.watchdog_raw,
            args.watchdog_compact,
        )
    elif args.pair:
        if args.pair_watchdog_raws is None or args.pair_watchdog_compacts is None:
            raise SystemExit("--pair requires raw and compact watchdog pairs")
        result = check_pair(
            args.pair[0],
            args.pair[1],
            args.pair_watchdog_raws[0],
            args.pair_watchdog_compacts[0],
            args.pair_watchdog_raws[1],
            args.pair_watchdog_compacts[1],
        )
    else:
        if (
            args.aggregate_watchdog_raws is None
            or args.aggregate_watchdog_compacts is None
        ):
            raise SystemExit("--aggregate requires ten raw and ten compact watchdog reports")
        result = check_aggregate(
            args.aggregate[:5],
            args.aggregate[5:],
            args.aggregate_watchdog_raws[:5],
            args.aggregate_watchdog_compacts[:5],
            args.aggregate_watchdog_raws[5:],
            args.aggregate_watchdog_compacts[5:],
        )
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if result["status"] in {"PASS", "NOT_READY"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
