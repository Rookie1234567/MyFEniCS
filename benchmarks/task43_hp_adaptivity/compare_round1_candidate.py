"""Compare adaptive candidates, or explicitly diagnose frozen post-selection fields."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Mapping

import numpy as np
from dolfinx import fem
from mpi4py import MPI

from benchmarks.task43_hp_adaptivity import compare_initial_to_references as base
from benchmarks.task43_hp_adaptivity.candidate_records import (
    load_accepted_parent_artifacts,
)
from benchmarks.task43_hp_adaptivity.h100_anchor import (
    _V12_RECOVERY_MANIFEST_REL,
    _load_v16_p8_context,
    _check_v11_runtime_envelope,
    _assert_mesh_profile,
    _h100_config,
    _load_v11_primary_contract,
    _load_v12_execution_recovery_manifest,
    _resolve_v12_p2_source,
    _sha256_file,
    _v11_input_snapshot,
    _v11_source_snapshot,
    _verify_v12_p2_source_binding,
    _require_v11_watchdog_worker_identity,
    _v11_raw_vector_gates,
    _verify_v16_p8_source_snapshot,
    _validate_round1_candidate_inputs,
    task43_v2_physical_configuration_identity,
)
from benchmarks.task43_hp_adaptivity.candidate_checkpoints import (
    _array_identity as _checkpoint_array_identity,
    write_atomic_json,
    write_atomic_npz,
)
from src.runners.physical_intermediate import WorkflowLedger
from benchmarks.task43_hp_adaptivity.profile import _mode_identity
from benchmarks.task43_hp_adaptivity.reference_restore import _post_selection_binding
from src.adaptivity.physical_g_error import (
    accumulate_physical_g_cell_contributions,
    dorfler_mark_physical_g,
)
from src.adaptivity.stage4_local_h import build_stage4_local_h_mesh_data
from src.common.modes_3d import incident_power_3d, outgoing_port_modes_3d
from src.postprocessing.physical_field_comparison import build_common_volume_quadrature
from src.postprocessing.physical_field_sampling import (
    prepare_cell_local_vector_field_export,
    sample_cell_local_vector_fields,
)
from src.solvers.common_3d_solve import _create_nedelec_space
from src.solvers.dtn_port_3d import (
    _mode_boundary_phase,
    _mode_carries_outward_power,
    _mode_power_at_boundary,
)

ROOT = Path(__file__).resolve().parents[2]
CURRENT_RUN = ROOT / "benchmarks/artifacts/task43/current_180/attempt1/run"
REFERENCE_ROOT = ROOT / "benchmarks/artifacts/task43/reference_imports/attempt2"
REFERENCE_COMPARISON = ROOT / "benchmarks/artifacts/task43/reference_comparison/attempt2"
ACCEPTANCE = ROOT / "docs/task43_hp_adaptivity/outcomes/records/round1_acceptance_contract_v1.json"
COMPARISON_CONTRACT = ROOT / "docs/task43_hp_adaptivity/outcomes/records/comparison_contract_v1.json"
CANDIDATE_RECORDS = Path(__file__).with_name("candidate_records.py")
DEFAULT_OUTPUT = ROOT / "benchmarks/artifacts/task43/round1_candidates/comparisons"
_V11_P5_INPUT_ROLES = {
    "R9_authority_plan",
    "R9_candidate_plan_copy",
    "R9_candidate_storage",
    "R9_candidate_record",
    "R9_selection_transition",
    "R9_comparison",
    "R8_ancestry_selection",
    "frozen_acceptance_contract",
    "frozen_comparison_contract",
    "reference_calibration",
    "Y6_1_auxiliary_amplitudes",
    "Y6_1_modal_orders",
    "Y6_1_saved_samples_metadata",
    "Y6_1_saved_samples",
    "Y6_1_native_summary",
    "Y6_1_carrier_coefficients",
    "Y6_1_recovered_bundle",
    "Y6_1_resolved_config",
    "Y6_1_restore_identity",
    "Y6_1_restore_inventory",
}
_V15_H_SAVED_PRIMARY_BINDING_PATH = Path(
    "docs/task43_hp_adaptivity/outcomes/records/v15_h_saved_primary_recovery_binding.json"
)
_V15_H_SAVED_PRIMARY_BINDING_SHA256 = (
    "4e7e23d9fab8f46a34428d8cab76ad9d2a38bac3b99364b5e0deeb7615d6fc04"
)
_V15_H_HISTORICAL_SOURCE_DIFFERENCES = {
    "benchmarks/task43_hp_adaptivity/h100_anchor.py",
    "benchmarks/task43_hp_adaptivity/compare_round1_candidate.py",
    "src/test/test_task43_v11_scientific_restart.py",
}
_V15_H_FIXED_INPUT_NAMES = {
    "run/task43_v11_partial_terminal.json",
    "run/primary_state.npz",
    "run/primary_raw_vector_audit.json",
    "run/pre_validation_checkpoint.json",
    "run/pre_validation_checkpoint.npz",
    "run/candidate_plan.json",
    "run/solve/dtn_port_diffraction_orders_3d.json",
    "run/solve/dtn_port_power_metrics_3d.json",
    "run/solve/dtn_auxiliary_amplitudes_3d.json",
    "run/solve/volume_absorption.json",
    "snapshots/launch_manifest.json",
    "snapshots/launch.sh",
    "watchdog/summary.json",
    "launcher_exit_code.txt",
    "watchdog_exit_code.txt",
    "source_head.txt",
}


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _v12_p5_input_snapshot(
    candidate_run_root: Path,
    *,
    contract_sha256: str,
    recovery_binding: dict[str, Any],
    saved_primary_binding_path: Path | None = None,
) -> dict[str, dict[str, str]]:
    """Hash the root-joined P2 source and every P4 byte consumed by P5."""

    if saved_primary_binding_path is not None:
        return _v15_h_saved_primary_input_snapshot(
            candidate_run_root,
            saved_primary_binding_path=saved_primary_binding_path,
            contract_sha256=contract_sha256,
            recovery_binding=recovery_binding,
        )

    attempt_root = candidate_run_root.resolve().parent
    snapshot = _verify_v12_p2_source_binding(
        recovery_binding,
        contract_sha256=contract_sha256,
        p4_launch_manifest_path=attempt_root / "snapshots/launch_manifest.json",
    )
    paths = (
        candidate_run_root / "candidate_plan.json",
        candidate_run_root / "task43_round1_candidate_record.json",
        candidate_run_root / "task43_v11_primary_terminal.json",
        candidate_run_root / "primary_state.npz",
        candidate_run_root / "primary_raw_vector_audit.json",
        candidate_run_root / "candidate_recovered_solution_storage.npz",
        candidate_run_root / "solve/dtn_port_diffraction_orders_3d.json",
        attempt_root / "snapshots/launch_manifest.json",
        attempt_root / "snapshots/launch.sh",
        attempt_root / "watchdog/summary.json",
        attempt_root / "launcher_exit_code.txt",
        attempt_root / "watchdog_exit_code.txt",
    )
    for path in paths:
        resolved = path.resolve()
        if not resolved.is_file():
            raise FileNotFoundError(f"V12 P5 input is missing: {resolved}")
        snapshot[str(resolved)] = {"path": str(resolved), "sha256": _sha256_file(resolved)}
    terminal = _json(candidate_run_root / "task43_v11_primary_terminal.json")
    record = _json(candidate_run_root / "task43_round1_candidate_record.json")
    if (
        terminal.get("v12_recovery_binding") != recovery_binding
        or record.get("candidate_identity", {}).get("v12_recovery_binding")
        != recovery_binding
        or record.get("source_identity", {}).get("v12_recovery_binding")
        != recovery_binding
    ):
        raise ValueError("V12 P5 P4 endpoint/terminal does not bind the chosen P2 source")
    return snapshot


def _v15_h_saved_primary_input_snapshot(
    candidate_run_root: Path,
    *,
    saved_primary_binding_path: Path,
    contract_sha256: str,
    recovery_binding: dict[str, Any],
) -> dict[str, dict[str, str]]:
    binding, snapshot, _terminal = _v15_h_saved_primary_binding_and_inputs(
        candidate_run_root,
        binding_path=saved_primary_binding_path,
        contract_sha256=contract_sha256,
        recovery_binding=recovery_binding,
    )
    terminal_path = candidate_run_root / "task43_v11_partial_terminal.json"
    if _sha256_file(terminal_path) != binding.get("failed_terminal_sha256"):
        raise RuntimeError("V15 P4 FAILED terminal changed during the P5 input snapshot")
    if _sha256_file(saved_primary_binding_path) != _V15_H_SAVED_PRIMARY_BINDING_SHA256:
        raise RuntimeError("V15 saved-primary binding changed during the P5 input snapshot")
    return snapshot


def _canonical_json_sha256(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _v15_h_saved_primary_binding_and_inputs(
    candidate_run_root: Path,
    *,
    binding_path: Path,
    contract_sha256: str,
    recovery_binding: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, dict[str, str]], dict[str, Any]]:
    expected_binding_path = (ROOT / _V15_H_SAVED_PRIMARY_BINDING_PATH).resolve()
    binding_path = Path(binding_path).resolve()
    if (
        binding_path != expected_binding_path
        or not binding_path.is_file()
        or _sha256_file(binding_path) != _V15_H_SAVED_PRIMARY_BINDING_SHA256
    ):
        raise ValueError("V15 P5 requires the fixed saved-primary recovery binding")
    binding = _json(binding_path)
    if (
        binding.get("schema") != "task43.v15.p4-saved-primary-binding.v1"
        or Path(str(binding.get("source_root", ""))).resolve() != candidate_run_root.resolve()
        or binding.get("contract", {}).get("sha256") != contract_sha256
        or binding.get("recovery_manifest", {}).get("sha256")
        != recovery_binding.get("manifest_sha256")
        or binding.get("v12_recovery_binding") != recovery_binding
    ):
        raise ValueError("V15 P5 saved-primary binding changes its fixed source identity")

    terminal_path = candidate_run_root / "task43_v11_partial_terminal.json"
    terminal_sha256 = _sha256_file(terminal_path)
    terminal = _json(terminal_path)
    if (
        terminal.get("schema") != "task43.v11.partial-terminal.v1"
        or terminal.get("phase") != "R9_H8"
        or terminal.get("status") != "FAILED"
        or terminal.get("official_result") is not False
        or terminal.get("passed") is not False
        or terminal.get("selection_eligible") is not False
        or terminal.get("continuation_all_false") is not True
        or terminal.get("source_identity", {}).get("git_head")
        != binding.get("source_head")
        or binding.get("failed_terminal_sha256") != terminal_sha256
        or terminal.get("v12_recovery_binding") != recovery_binding
    ):
        raise ValueError("V15 P5 source is not the bound immutable FAILED P4 terminal")
    if candidate_run_root.resolve() != Path(str(binding["source_root"])):
        raise ValueError("V15 P5 saved-primary source root is not canonical")

    documents = (
        "contract",
        "recovery_manifest",
        "prior_user_authorization",
        "failed_attempt_closeout",
        "root_raw_recheck",
        "p2_joined_terminal",
    )
    snapshot: dict[str, dict[str, str]] = {}
    for name in documents:
        item = binding.get(name)
        if not isinstance(item, dict):
            raise ValueError(f"V15 P5 binding lacks {name} identity")
        path = Path(str(item.get("path", "")))
        digest = str(item.get("sha256", ""))
        if (
            not path.is_absolute()
            or path.is_symlink()
            or path.resolve() != path
            or not path.is_file()
            or _sha256_file(path) != digest
        ):
            raise ValueError(f"V15 P5 bound {name} bytes differ")
        snapshot[str(path)] = {"path": str(path), "sha256": digest}

    if binding["contract"]["path"] != str(
        (ROOT / "docs/task43_hp_adaptivity/outcomes/records/v11_scientific_restart_contract.json").resolve()
    ):
        raise ValueError("V15 P5 binding changes the frozen contract path")
    if binding["recovery_manifest"]["path"] != str(
        (ROOT / _V12_RECOVERY_MANIFEST_REL).resolve()
    ):
        raise ValueError("V15 P5 binding changes the frozen V12 recovery manifest path")
    if binding["p2_joined_terminal"]["path"] != str(
        (Path(recovery_binding["support_root"]) / "v12_p2_joined_terminal.json").resolve()
    ):
        raise ValueError("V15 P5 binding changes the root-joined P2 terminal")
    closeout = _json(Path(binding["failed_attempt_closeout"]["path"]))
    raw_recheck = _json(Path(binding["root_raw_recheck"]["path"]))
    if (
        closeout.get("status") != "FAILED_SUMMARY_NUMPY_SERIALIZATION_AFTER_SOLVE"
        or closeout.get("source_head") != binding.get("source_head")
        or closeout.get("raw_numerical_gates_pass") is not True
        or closeout.get("original_endpoint") != "FAILED"
        or raw_recheck.get("numerical_gates_pass") is not True
    ):
        raise ValueError("V15 P5 prior failed endpoint or raw recheck changed")

    fixed_inputs = binding.get("fixed_inputs")
    if not isinstance(fixed_inputs, dict) or set(fixed_inputs) != _V15_H_FIXED_INPUT_NAMES:
        raise ValueError("V15 P5 saved-primary binding omits a fixed P4 input")
    for name in sorted(_V15_H_FIXED_INPUT_NAMES):
        item = fixed_inputs[name]
        if not isinstance(item, dict):
            raise ValueError(f"V15 P5 fixed input {name} is malformed")
        expected_path = (
            candidate_run_root / name.removeprefix("run/")
            if name.startswith("run/")
            else candidate_run_root.parent / name
        ).resolve()
        path = Path(str(item.get("path", "")))
        digest = str(item.get("sha256", ""))
        if (
            path != expected_path
            or path.is_symlink()
            or not path.is_file()
            or _sha256_file(path) != digest
        ):
            raise ValueError(f"V15 P5 saved-primary input changed: {name}")
        snapshot[str(path)] = {"path": str(path), "sha256": digest}

    p4_manifest_path = candidate_run_root.parent / "snapshots/launch_manifest.json"
    p4_manifest = _json(p4_manifest_path)
    source_head_path = candidate_run_root.parent / "source_head.txt"
    if (
        source_head_path.read_text(encoding="ascii").strip() != binding.get("source_head")
        or p4_manifest.get("head") != binding.get("source_head")
    ):
        raise ValueError("V15 P4 source HEAD differs across terminal and launch records")

    if binding.get("failed_terminal_sha256") != terminal_sha256:
        raise RuntimeError("V15 P4 FAILED terminal changed after its first read")
    p2_snapshot = _verify_v12_p2_source_binding(
        recovery_binding,
        contract_sha256=contract_sha256,
        p4_launch_manifest_path=candidate_run_root.parent
        / "snapshots/launch_manifest.json",
        allow_historical_p4_sources=True,
    )
    snapshot.update(p2_snapshot)
    snapshot[str(binding_path)] = {
        "path": str(binding_path),
        "sha256": _V15_H_SAVED_PRIMARY_BINDING_SHA256,
    }
    return binding, snapshot, terminal


def _v15_restore_h_saved_primary_candidate(
    candidate_run_root: Path,
    output_root: Path,
    *,
    contract_sha256: str,
    recovery_binding: dict[str, Any],
    saved_binding: dict[str, Any],
    terminal: dict[str, Any],
) -> dict[str, Any]:
    """Restore only the hash-bound P4 primary field; never claim a successful P4 endpoint."""

    packet_record = terminal["primary_packet"]
    packet_path = candidate_run_root / "primary_state.npz"
    packet_identity = packet_record.get("identity")
    if (
        not isinstance(packet_identity, dict)
        or _canonical_json_sha256(packet_identity)
        != saved_binding.get("primary_packet_identity_sha256")
        or packet_record.get("npz_sha256")
        != saved_binding["fixed_inputs"]["run/primary_state.npz"]["sha256"]
        or Path(str(packet_record.get("npz_path", ""))).resolve() != packet_path.resolve()
    ):
        raise ValueError("V15 P5 primary packet identity differs from its fixed binding")
    with np.load(packet_path, allow_pickle=False) as archive:
        if "__task43_record_json__" not in archive.files:
            raise ValueError("V15 P5 primary packet lacks its embedded identity")
        embedded = json.loads(
            np.asarray(archive["__task43_record_json__"], dtype=np.uint8).tobytes()
        )
        packet_arrays = {
            name: np.asarray(archive[name]).copy()
            for name in archive.files
            if name != "__task43_record_json__"
        }
    if (
        embedded.get("schema") != "task43.v11.primary_state.v1"
        or embedded.get("identity") != packet_identity
        or embedded.get("arrays") != packet_record.get("arrays")
        or set(packet_arrays) != set(packet_record.get("arrays", {}))
        or _canonical_json_sha256(embedded.get("identity"))
        != saved_binding.get("primary_packet_identity_sha256")
    ):
        raise ValueError("V15 P5 primary packet embedded identity differs")
    for name, array in packet_arrays.items():
        actual = _checkpoint_array_identity(array)
        declared = packet_record["arrays"].get(name, {})
        if any(actual.get(key) != declared.get(key) for key in ("dtype", "shape", "sha256")):
            raise ValueError(f"V15 P5 primary packet array identity differs: {name}")

    candidate_identity = packet_identity.get("candidate_identity", {})
    endpoint_identity = packet_identity.get("endpoint_identity", {})
    actual_cfg = endpoint_identity.get("actual_cfg", {})
    controls = endpoint_identity.get("numerical_controls", {})
    if (
        packet_identity.get("phase") != "R9_H8"
        or packet_identity.get("contract_sha256") != contract_sha256
        or candidate_identity.get("candidate_id") != "v11_r9_h8"
        or candidate_identity.get("action") != "h_refine"
        or candidate_identity.get("v12_recovery_binding") != recovery_binding
        or packet_identity.get("source_identity") != terminal.get("source_identity")
        or terminal.get("candidate_identity") != candidate_identity
        or terminal.get("v12_recovery_binding") != recovery_binding
        or endpoint_identity.get("schema") != "task43.v11.primary_endpoint_identity.v1"
    ):
        raise ValueError("V15 P5 saved primary is not the failed R9_H8 state bound to P2")

    plan_path = candidate_run_root / "candidate_plan.json"
    plan_sha256 = _sha256_file(plan_path)
    plan = _json(plan_path)
    if (
        plan_sha256 != packet_identity.get("candidate_plan_sha256")
        or candidate_identity.get("plan_sha256") != plan_sha256
        or plan.get("task43_candidate", {}).get("candidate_id") != "v11_r9_h8"
        or plan.get("task43_candidate", {}).get("action") != "h_refine"
        or plan.get("task43_candidate", {}).get("provenance", {}).get(
            "v12_recovery_binding"
        ) != recovery_binding
    ):
        raise ValueError("V15 P5 saved primary does not use the fixed P2 h-refinement plan")

    prevalidation_path = candidate_run_root / "pre_validation_checkpoint.json"
    prevalidation = _json(prevalidation_path)
    if (
        _canonical_json_sha256(prevalidation.get("identity"))
        != saved_binding.get("prevalidation_identity_sha256")
        or prevalidation.get("identity")
        != packet_identity.get("pre_validation_checkpoint", {}).get("identity")
        or prevalidation.get("npz_sha256")
        != saved_binding["fixed_inputs"]["run/pre_validation_checkpoint.npz"]["sha256"]
    ):
        raise ValueError("V15 P5 pre-validation identity differs from the fixed primary")
    with np.load(candidate_run_root / "pre_validation_checkpoint.npz", allow_pickle=False) as archive:
        checkpoint_arrays = {name: np.asarray(archive[name]).copy() for name in archive.files}
    declared_checkpoint_arrays = prevalidation.get("arrays", {})
    if set(checkpoint_arrays) != set(declared_checkpoint_arrays):
        raise ValueError("V15 P5 pre-validation array inventory differs")
    for name, values in checkpoint_arrays.items():
        actual = _checkpoint_array_identity(values)
        if any(
            actual.get(key) != declared_checkpoint_arrays[name].get(key)
            for key in ("dtype", "shape", "sha256")
        ):
            raise ValueError(f"V15 P5 pre-validation array identity differs: {name}")
        packet_array = packet_arrays.get("recovered_" + name)
        if (
            packet_array is None
            or packet_array.dtype != values.dtype
            or packet_array.shape != values.shape
            or not np.array_equal(packet_array, values)
        ):
            raise ValueError(f"V15 P5 primary and pre-validation arrays differ: {name}")

    raw_path = candidate_run_root / "primary_raw_vector_audit.json"
    raw_checkpoint = _json(raw_path)
    recomputed_raw = _v11_raw_vector_gates(
        packet_arrays,
        active_trace_rows=int(packet_identity["P2_preassembly_space_audit"]["actual"]["independent_trace_rows"]),
        active_interior_rows=int(packet_identity["P2_preassembly_space_audit"]["actual"]["active_cell_interior_rows"]),
        independent_fe_dofs=int(packet_identity["independent_active_fe_dofs"]),
        active_full_rows=int(packet_identity["raw_full_active_scope"]["active_full_rows"]),
        full_active_scope=packet_identity["raw_full_active_scope"],
        independent_a6_scope=packet_identity["independent_A6_raw_vector_scope"],
        normal_correction_count=int(packet_identity["normal_correction_count"]),
        normal_converged_reason=int(
            packet_identity["normal_correction_audit"]["correction_ksp"]["converged_reason"]
        ),
        normal_correction_status=str(packet_identity["normal_correction_audit"]["status"]),
        extra_correction_count=int(packet_identity["extra_correction_count"]),
    )
    if (
        raw_checkpoint.get("schema") != "task43.v11.primary_raw_vector_audit_checkpoint.v1"
        or raw_checkpoint.get("pass") is not True
        or raw_checkpoint.get("audit") != recomputed_raw
        or recomputed_raw.get("pass") is not True
    ):
        raise ValueError("V15 P5 saved primary failed independent raw-vector gates")

    p2_plan_path = Path(str(recovery_binding["plan_output_path"]))
    p2_audit = _json(Path(str(recovery_binding["audit_path"])))
    p4_space = packet_identity.get("P2_preassembly_space_audit", {})
    p4_actual = p4_space.get("actual", {})
    p2_dofs = p2_audit.get("dofs", {})
    if (
        p4_space.get("pass") is not True
        or p4_space.get("p2_plan_sha256") != _sha256_file(p2_plan_path)
        or p4_space.get("p2_audit_sha256") != _sha256_file(Path(str(recovery_binding["audit_path"])))
        or p4_actual.get("independent_active_fe_dofs")
        != p2_dofs.get("independent_active_fe_dofs")
        or p4_actual.get("independent_trace_rows") != p2_dofs.get("independent_trace_rows")
        or p4_actual.get("active_cell_interior_rows")
        != p2_dofs.get("active_cell_interior_rows")
        or p4_actual.get("cell_interior_histogram")
        != p2_audit.get("degrees", {}).get("cell_interior_histogram")
    ):
        raise ValueError("V15 P5 primary actual P2 space audit does not match its joined plan")

    cfg = _h100_config(
        kind="empty_h_active_p3",
        case_name=str(actual_cfg["case_name"]),
        geometry_profile="initial_180",
    )
    cfg.stage4_local_h_refinement_plan = str(plan_path)
    mesh_data = build_stage4_local_h_mesh_data(cfg, plan_path, comm=MPI.COMM_WORLD)
    mesh = mesh_data.mesh
    axes = base._axes_from_mesh(mesh)
    axes_record = {name: np.asarray(axis, dtype=np.float64).tolist() for name, axis in zip(("x", "y", "z"), axes, strict=True)}
    if axes_record != prevalidation["identity"].get("resolved_axes_nm"):
        raise ValueError("V15 P5 restored mesh axes differ from the primary checkpoint")
    mesh_audit = _assert_mesh_profile(
        mesh_data,
        axes,
        "candidate_initial180",
        candidate_plan=plan,
        candidate_plan_sha256=plan_sha256,
    )
    expected_physical = task43_v2_physical_configuration_identity(
        cfg.as_jsonable(),
        axis_values_nm=axes_record,
        candidate_plan_sha256=plan_sha256,
        active_degree_plan_sha256=str(prevalidation["identity"]["active_degree_plan_sha256"]),
    )
    if expected_physical != endpoint_identity.get("physical_configuration"):
        raise ValueError("V15 P5 rebuilt physical configuration differs from the saved endpoint")
    space = _create_nedelec_space(mesh, cfg)
    actual_arrays = base._actual_mesh_identity(mesh, space)
    expected_array_keys = {
        "mesh_geometry_coordinates_nm": "mesh_geometry_coordinates_nm",
        "mesh_geometry_dofmap": "mesh_geometry_dofmap",
        "mesh_owned_cell_global_ids": "mesh_owned_cell_global_ids",
        "mesh_cell_vertex_dofmap": "mesh_cell_vertex_dofmap",
        "p6_function_space_cell_dofmap": "p6_function_space_dofmap",
        "p6_owned_global_dof_block_ids": "p6_owned_global_dof_block_ids",
        "p6_ghost_global_dof_block_ids": "p6_ghost_global_dof_block_ids",
    }
    restored_identities: dict[str, Any] = {}
    for identity_key, storage_key in expected_array_keys.items():
        expected_values = packet_arrays.get("recovered_" + storage_key)
        actual_values = np.asarray(actual_arrays[identity_key])
        checkpoint_values = checkpoint_arrays.get(storage_key)
        if (
            expected_values is None
            or checkpoint_values is None
            or expected_values.dtype != actual_values.dtype
            or expected_values.shape != actual_values.shape
            or not np.array_equal(expected_values, actual_values)
            or not np.array_equal(checkpoint_values, actual_values)
        ):
            raise ValueError(f"V15 P5 restored mesh identity differs: {identity_key}")
        restored_identities[storage_key] = _checkpoint_array_identity(actual_values)
    coefficients = np.asarray(packet_arrays["recovered_recovered_p6_local_coefficients"]).copy()
    if (
        not np.array_equal(coefficients, checkpoint_arrays["recovered_p6_local_coefficients"])
        or not np.array_equal(coefficients, packet_arrays["recovered_recovered_p6_owned_coefficients"])
    ):
        raise ValueError("V15 P5 recovered P6 coefficient arrays differ")
    field = fem.Function(space, name="v11_r9_h8_saved_primary_E")
    if field.x.array.shape != coefficients.shape:
        raise ValueError("V15 P5 saved P6 carrier shape differs from rebuilt function space")
    field.x.array[:] = coefficients
    field.x.scatter_forward()

    power_metrics = _json(candidate_run_root / "solve/dtn_port_power_metrics_3d.json")
    mode_payload = _json(candidate_run_root / "solve/dtn_port_diffraction_orders_3d.json")
    numerical_controls = {
        "volume_quadrature_degree": int(controls["quadrature_degree"]["volume"]),
        "incident_and_port_quadrature_degree": int(power_metrics["stage4_dtn_surface_quadrature_degree"]),
        "volume_quadrature_rule": str(controls["A_volume_resolved_rule"]["quadrature_rule"]),
        "sparse_cutoff_policy": str(power_metrics["stage4_dtn_sparse_cutoff_policy"]),
        "sparse_cutoff_relative_tolerance": float(power_metrics["stage4_dtn_sparse_cutoff_relative_tolerance"]),
        "ordered_mode_count": int(controls["modal_selection"]["count"]),
        "port_amplitude_scale_policy": str(power_metrics["dtn_port_boundary_amplitude_scale_policy"]),
        "mesh": mesh_audit,
        "nedelec_degree": int(actual_cfg["nedelec_degree"]),
        "active_space": {"independent_active_fe_dofs": int(packet_identity["independent_active_fe_dofs"])},
        "assembly_backend": str(controls["assembly_backend"]),
    }
    adapter_record = {
        "schema": "task43.v15.saved-primary-p4-adapter.v1",
        "classification": "restored_failed_p4_primary_for_nonofficial_p5_diagnostic",
        "original_endpoint_status": "FAILED",
        "candidate_identity": candidate_identity,
        "source_identity": packet_identity["source_identity"],
        "v12_recovery_binding": recovery_binding,
        "p4_preassembly_space_audit": p4_space,
        "numerical_controls": numerical_controls,
        "resolved_config": {"floquet_constraint_mode": str(actual_cfg["floquet_constraint_mode"])},
        "resolved_identity": {
            "nedelec_degree": numerical_controls["nedelec_degree"],
            "floquet_constraint_mode": str(actual_cfg["floquet_constraint_mode"]),
            "ordered_mode_count": numerical_controls["ordered_mode_count"],
            "mesh_axes_nm": mesh_audit["axes_nm"],
        },
        "recovered_solution_storage": {
            "active_trace_rows": int(p4_actual["independent_trace_rows"]),
            "active_cell_interior_rows": int(p4_actual["active_cell_interior_rows"]),
            "independent_active_fe_dofs": int(packet_identity["independent_active_fe_dofs"]),
        },
        "solver": {"route_identity": "not_recorded_in_failed_primary_endpoint"},
        "method": "not_recorded_in_failed_primary_endpoint",
        "power": {
            "channel_rows_sha256": _sha256_file(candidate_run_root / "solve/dtn_port_diffraction_orders_3d.json"),
            "aggregate": {
                key: float(power_metrics[key])
                for key in ("R_total", "T_total", "R00_s", "R00_p", "R00_total")
            },
            "A_volume_total": float(power_metrics["A_volume_total"]),
        },
    }
    recovery_identity = {
        "schema": "task43.v15.saved-primary-p4-restoration.v1",
        "classification": "restored_failed_primary_for_nonofficial_union_comparison",
        "original_status": "FAILED",
        "original_partial_terminal_path": str((candidate_run_root / "task43_v11_partial_terminal.json").resolve()),
        "original_partial_terminal_sha256": _sha256_file(candidate_run_root / "task43_v11_partial_terminal.json"),
        "binding_path": str((ROOT / _V15_H_SAVED_PRIMARY_BINDING_PATH).resolve()),
        "binding_sha256": _V15_H_SAVED_PRIMARY_BINDING_SHA256,
        "primary_packet_path": str(packet_path.resolve()),
        "primary_packet_sha256": _sha256_file(packet_path),
        "prevalidation_identity_sha256": saved_binding["prevalidation_identity_sha256"],
        "candidate_plan_sha256": plan_sha256,
        "v12_recovery_binding": recovery_binding,
        "mesh_profile": mesh_audit,
        "restored_array_identities": restored_identities,
        "active_fe_dofs": int(packet_identity["independent_active_fe_dofs"]),
        "ordered_mode_count": int(controls["modal_selection"]["count"]),
        "official_result": False,
        "passed": False,
        "selection_transition_written": False,
    }
    recovery_root = Path(str(saved_binding["output_root"])).resolve()
    expected_output_root = (output_root / "saved_primary_recovery").resolve()
    if recovery_root != expected_output_root or recovery_root.exists():
        raise FileExistsError("V15 P5 saved-primary derived output root is not its one empty bound path")
    recovery_root.mkdir(parents=True, exist_ok=False)
    recovery_record_path = recovery_root / "restoration_identity.json"
    recovery_record_path.write_text(
        json.dumps(recovery_identity, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return {
        "label": "v11_r9_h8",
        "candidate_id": "v11_r9_h8",
        "candidate_action": "h_refine",
        "cfg": cfg,
        "mesh_data": mesh_data,
        "field": field,
        "axes": axes,
        "record": adapter_record,
        "mode_payload": mode_payload,
        "power": {
            **adapter_record["power"]["aggregate"],
            "A_volume": adapter_record["power"]["A_volume_total"],
        },
        "mesh_identity": {
            name: base._array_identity(values) for name, values in actual_arrays.items()
        },
        "storage_sha256": _sha256_file(packet_path),
        "plan_sha256": plan_sha256,
        "v12_restoration_binding": {
            "p2_source_id": recovery_binding["p2_source_id"],
            "recovery_manifest_sha256": recovery_binding["manifest_sha256"],
            "primary_packet_sha256": _sha256_file(packet_path),
            "same_array_values_dtype_and_shape": True,
            "recovery_array_identities": restored_identities,
        },
        "saved_primary_recovery": {
            "path": str(recovery_record_path.resolve()),
            "sha256": _sha256_file(recovery_record_path),
            "original_status": "FAILED",
        },
    }


def _sha256_bytes(values: np.ndarray) -> str:
    array = np.ascontiguousarray(values)
    digest = hashlib.sha256()
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(json.dumps(list(array.shape)).encode("ascii"))
    digest.update(array.view(np.uint8))
    return digest.hexdigest()


def _load_modal_case(label: str) -> dict[str, Any]:
    if label == "current_180":
        record_path = CURRENT_RUN / "task43_initial180_current_record.json"
        orders_path = CURRENT_RUN / "solve/dtn_port_diffraction_orders_3d.json"
        record = _json(record_path)
        if record.get("gates", {}).get("pass") is not True:
            raise ValueError("frozen parent current did not pass its numerical gates")
        if _sha256_file(CURRENT_RUN / "recovered_solution_storage.npz") != record[
            "recovered_solution_storage"
        ]["sha256"]:
            raise ValueError("frozen parent field storage differs from its record")
        if _sha256_file(orders_path) != record["power"]["channel_rows_sha256"]:
            raise ValueError("frozen parent modal rows differ from their record")
        mode_payload = _json(orders_path)
        power = base._scalar_power_record(label, record, mode_payload)
        return {"label": label, "record": record, "mode_payload": mode_payload, "power": power}

    if label not in {"Y6_1", "Y6_2"}:
        raise ValueError("candidate comparison permits only Y6_1/Y6_2 modal records")
    case_root = REFERENCE_ROOT / label
    record = _json(case_root / "restore_identity_record.json")
    if record.get("status") != "RESTORATION_IDENTITY_PASS_NOT_TASK43_QUALIFIED":
        raise ValueError(f"{label} reference restoration identity is not valid")
    orders_path = case_root / "numerical_output/dtn_port_diffraction_orders_3d.json"
    expected_sha = record["input_artifacts"][
        "numerical_output/dtn_port_diffraction_orders_3d.json"
    ]["sha256"]
    if _sha256_file(orders_path) != expected_sha:
        raise ValueError("selection reference mode rows differ from their identity record")
    mode_payload = _json(orders_path)
    power = base._scalar_power_record(label, record, mode_payload)
    return {"label": label, "record": record, "mode_payload": mode_payload, "power": power}


def _restore_case_fields(
    label: str, output_root: Path, *, reference_root: Path | None = None,
    post_selection_record: Path | None = None, assets_manifest: Path | None = None,
) -> dict[str, Any]:
    loaded = base._load_field_case(
        label, output_root, reference_root=reference_root,
        post_selection_record=post_selection_record, assets_manifest=assets_manifest,
    )
    label, cfg, mesh_data, coefficients, expected_arrays, record, mode_payload = loaded
    mesh = mesh_data.mesh
    if mesh.comm.size != 1:
        raise RuntimeError(f"{label} reconstructed mesh is not serial")
    space = _create_nedelec_space(mesh, cfg)
    actual_arrays = base._actual_mesh_identity(mesh, space)
    for name in base._IDENTITY_ARRAYS:
        if not np.array_equal(actual_arrays[name], expected_arrays[name]):
            raise ValueError(f"{label} reconstructed {name} differs from stored identity")
    field = fem.Function(space, name=f"{label}_full_recovered_E")
    if field.x.array.shape != coefficients.shape:
        raise ValueError(f"{label} coefficient vector differs from reconstructed space")
    field.x.array[:] = coefficients
    field.x.scatter_forward()
    return {
        "label": label,
        "cfg": cfg,
        "mesh_data": mesh_data,
        "field": field,
        "axes": base._axes_from_mesh(mesh),
        "record": record,
        "mode_payload": mode_payload,
        "power": base._scalar_power_record(label, record, mode_payload),
        "mesh_identity": {name: base._array_identity(values) for name, values in actual_arrays.items()},
    }


def _validate_v11_pending_candidate(
    candidate_run_root: Path,
    *,
    record: dict[str, Any],
    contract: dict[str, Any],
    contract_sha256: str,
    recovery_binding: dict[str, Any],
) -> tuple[Path, dict[str, Any], str]:
    """Require the one successful P4 pending endpoint and its full byte chain."""

    candidate_root = (
        Path(str(contract["artifact_prefix"]))
        / str(contract["phases"]["P4"]["root"])
        / "run"
    ).resolve()
    if candidate_run_root.resolve() != candidate_root:
        raise ValueError("V11 pending restore requires the unique P4 run root")
    attempt_root = candidate_root.parent
    _verify_v12_p2_source_binding(
        recovery_binding,
        contract_sha256=contract_sha256,
        p4_launch_manifest_path=attempt_root / "snapshots/launch_manifest.json",
    )
    for filename in ("launcher_exit_code.txt", "watchdog_exit_code.txt"):
        code_path = attempt_root / filename
        if not code_path.is_file() or code_path.read_text(encoding="ascii").strip() != "0":
            raise ValueError(f"V11 P4 {filename} does not record a zero exit")
    watchdog_summary_path = attempt_root / "watchdog/summary.json"
    manifest_path = attempt_root / "snapshots/launch_manifest.json"
    launch_snapshot_path = attempt_root / "snapshots/launch.sh"
    if not all(path.is_file() for path in (watchdog_summary_path, manifest_path, launch_snapshot_path)):
        raise ValueError("V11 P4 watchdog summary or launch identity snapshot is missing")
    watchdog_summary = _json(watchdog_summary_path)
    manifest = _json(manifest_path)
    expected_script = (
        Path(str(contract["artifact_prefix"]))
        / contract["phases"]["P4"]["script"]
    ).resolve()
    if (
        watchdog_summary.get("classification") != "COMPLETED"
        or watchdog_summary.get("leader_exit_code") != 0
        or watchdog_summary.get("descendants_cleared") is not True
        or watchdog_summary.get("remaining_child_pids") != []
        or manifest.get("schema") != "task43.v11.launch-input-manifest.v1"
        or manifest.get("contract_sha256") != contract_sha256
        or manifest.get("recovery_manifest_sha256")
        != recovery_binding.get("manifest_sha256")
        or manifest.get("p2_source_id") != recovery_binding.get("p2_source_id")
        or _sha256_file(launch_snapshot_path) != manifest.get("launch_shell_sha256")
        or _sha256_file(expected_script) != _sha256_file(launch_snapshot_path)
    ):
        raise ValueError("V11 P4 launch manifest, watchdog exit or descendant cleanup is invalid")
    manifest_source = {
        str(item["path"]): str(item["sha256"])
        for item in manifest.get("source", [])
        if isinstance(item, dict) and "path" in item and "sha256" in item
    }
    manifest_inputs = {
        str(Path(item["path"]).resolve()): str(item["sha256"])
        for item in manifest.get("inputs", [])
        if isinstance(item, dict) and "path" in item and "sha256" in item
    }
    for item in contract.get("inputs", []):
        input_path = (ROOT / str(item["path"])).resolve()
        if manifest_inputs.get(str(input_path)) != item.get("sha256"):
            raise ValueError("V11 P4 launch manifest omits or changes a contract input")
    current_source = _v11_source_snapshot()
    expected_manifest_source = {
        **current_source,
        "docs/task43_hp_adaptivity/outcomes/records/v12_execution_recovery_manifest.json": recovery_binding[
            "manifest_sha256"
        ],
    }
    if manifest_source != expected_manifest_source:
        raise ValueError("V12 P4 launch source snapshot differs from the actual source")
    watchdog_identity = None
    endpoint_path = candidate_root / "task43_round1_candidate_record.json"
    terminal_path = candidate_root / "task43_v11_primary_terminal.json"
    partial_terminal_path = candidate_root / "task43_v11_partial_terminal.json"
    if partial_terminal_path.exists() or not terminal_path.is_file():
        raise ValueError("V11 P4 success terminal is missing or conflicts with a failure terminal")
    terminal = _json(terminal_path)
    if (
        terminal.get("schema") != "task43.v11.primary-terminal.v1"
        or terminal.get("phase") != "R9_H8"
        or terminal.get("status") != "SOLVED_PENDING_POSTPROCESS"
        or terminal.get("official_result") is not False
        or terminal.get("passed") is not False
        or terminal.get("selection_eligible") is not False
        or terminal.get("selection_candidate") is not False
        or terminal.get("candidate_selected") is not False
        or terminal.get("continuation_all_false") is not True
        or terminal.get("contract_sha256") != contract_sha256
        or terminal.get("v12_recovery_binding") != recovery_binding
        or terminal.get("candidate_identity") != record.get("candidate_identity")
        or terminal.get("source_identity") != record.get("source_identity")
    ):
        raise ValueError("V11 P4 terminal is not the exact pending nonofficial endpoint")
    if terminal.get("endpoint_record_path") != str(endpoint_path):
        raise ValueError("V11 terminal names a different endpoint record path")
    endpoint_sha = _sha256_file(endpoint_path)
    if terminal.get("endpoint_record_sha256") != endpoint_sha:
        raise ValueError("V11 P4 terminal endpoint record hash differs")
    raw_checkpoint = record.get("primary_raw_vector_audit_checkpoint")
    terminal_raw_checkpoint = terminal.get("primary_raw_vector_audit_checkpoint")
    raw_checkpoint_path = (candidate_root / "primary_raw_vector_audit.json").resolve()
    if (
        not isinstance(raw_checkpoint, dict)
        or raw_checkpoint != terminal_raw_checkpoint
        or Path(str(raw_checkpoint.get("path", ""))).resolve() != raw_checkpoint_path
        or not raw_checkpoint_path.is_file()
        or _sha256_file(raw_checkpoint_path) != raw_checkpoint.get("sha256")
    ):
        raise ValueError("V11 P4 primary raw-gate checkpoint is missing or changed")
    raw_checkpoint_record = _json(raw_checkpoint_path)
    if (
        raw_checkpoint_record.get("schema")
        != "task43.v11.primary_raw_vector_audit_checkpoint.v1"
        or raw_checkpoint_record.get("pass") is not True
        or raw_checkpoint_record.get("audit")
        != record.get("primary_raw_vector_audit")
    ):
        raise ValueError("V11 P4 durable raw-gate checkpoint differs from its endpoint")
    candidate = record.get("candidate_identity")
    if (
        record.get("schema") != "task43.v11.primary-endpoint.v1"
        or record.get("phase") != "R9_H8"
        or record.get("status") != "SOLVED_PENDING_POSTPROCESS"
        or record.get("official_result") is not False
        or record.get("selection_eligible") is not False
        or record.get("selection_candidate") is not False
        or record.get("candidate_selected") is not False
        or record.get("continuation_all_false") is not True
        or record.get("gates", {}).get("pass") is not True
        or not isinstance(candidate, dict)
        or candidate.get("candidate_id") != "v11_r9_h8"
        or candidate.get("v11_phase") != "R9_H8"
        or candidate.get("v11_contract_sha256") != contract_sha256
        or candidate.get("v12_recovery_binding") != recovery_binding
    ):
        raise ValueError("V11 endpoint record does not match a successful P4 pending record")
    if record.get("solver", {}).get("official_result") is not False:
        raise ValueError("V11 pending endpoint carries an official-result flag")
    source_identity = record.get("source_identity")
    if not isinstance(source_identity, dict):
        raise ValueError("V11 pending endpoint lacks its source identity")
    source_contract = source_identity.get("v11_primary_contract", {})
    if (
        source_contract.get("contract_sha256") != contract_sha256
        or source_contract.get("phase") != "R9_H8"
        or Path(str(source_contract.get("contract_path", ""))).resolve()
        != (ROOT / "docs/task43_hp_adaptivity/outcomes/records/v11_scientific_restart_contract.json").resolve()
    ):
        raise ValueError("V11 P4 source identity is not bound to this frozen contract")
    if source_identity.get("v12_recovery_binding") != recovery_binding:
        raise ValueError("V12 P4 source identity differs from the selected P2 source")
    source_hashes = source_identity.get("file_sha256")
    if not isinstance(source_hashes, dict) or any(
        current_source.get(name) != digest for name, digest in source_hashes.items()
    ):
        raise ValueError("V11 P4 numerical source identity differs from the current frozen source")
    watchdog_identity = source_identity.get("v11_watchdog_worker_identity")
    if (
        not isinstance(watchdog_identity, dict)
        or watchdog_identity.get("direct_watchdog_parent_verified") is not True
        or watchdog_identity.get("tracer_descends_from_watchdog") is not True
        or not watchdog_identity.get("worker_tid_affinities")
        or any(item.get("cpu_list") != [1] for item in watchdog_identity["worker_tid_affinities"])
    ):
        raise ValueError("V11 P4 primary endpoint lacks its directly-parented traced CPU1 worker identity")
    for process_key, start_key in (
        ("worker_pid", "worker_start_ticks"),
        ("tracer_pid", "tracer_start_ticks"),
    ):
        proc_stat = Path(f"/proc/{int(watchdog_identity[process_key])}/stat")
        if proc_stat.is_file():
            fields = proc_stat.read_text(encoding="ascii").rsplit(")", 1)[1].split()
            if int(fields[19]) == int(watchdog_identity[start_key]):
                raise ValueError(f"V11 P4 {process_key} remains live after watchdog completion")
    if record.get("field_samples", {}).get("status") != "not_run_pending_p5_common_union_sampling":
        raise ValueError("V11 P4 must defer all field samples to the P5 union rule")
    endpoint_samples = record.get("primary_samples")
    terminal_samples = terminal.get("primary_samples")
    if endpoint_samples not in ({}, None) or terminal_samples not in ({}, None):
        raise ValueError("V11 P4 pending endpoint unexpectedly contains q8/q10 samples")
    plan_path = candidate_root / "candidate_plan.json"
    expected_plan = Path(str(recovery_binding["plan_output_path"])).resolve()
    plan_sha256 = _sha256_file(plan_path)
    expected_plan_sha = _sha256_file(expected_plan)
    if (
        plan_path.resolve() != (candidate_root / "candidate_plan.json").resolve()
        or plan_sha256 != record.get("candidate_plan_sha256")
        or plan_sha256 != terminal.get("candidate_plan_sha256")
        or plan_sha256 != candidate.get("plan_sha256")
        or plan_sha256 != expected_plan_sha
        or candidate.get("run_plan_path") != str(plan_path.resolve())
    ):
        raise ValueError("V11 P4 run-local plan differs from the unique P2 plan")
    plan = _json(plan_path)
    if (
        plan.get("task43_candidate", {}).get("candidate_id") != "v11_r9_h8"
        or plan.get("task43_candidate", {}).get("action") != "h_refine"
        or plan.get("task43_candidate", {}).get("provenance", {}).get(
            "v12_recovery_binding"
        ) != recovery_binding
    ):
        raise ValueError("V11 P4 plan is not the fixed h-refine candidate")
    packet = record.get("primary_packet")
    terminal_packet = terminal.get("primary_packet")
    if not isinstance(packet, dict) or not isinstance(terminal_packet, dict):
        raise ValueError("V11 P4 endpoint lacks its primary raw packet record")
    packet_path = (candidate_root / "primary_state.npz").resolve()
    if (
        Path(str(packet.get("npz_path", ""))).resolve() != packet_path
        or Path(str(terminal_packet.get("npz_path", ""))).resolve() != packet_path
        or not packet_path.is_file()
        or _sha256_file(packet_path) != packet.get("npz_sha256")
        or packet.get("npz_sha256") != terminal_packet.get("npz_sha256")
        or terminal_packet.get("identity") != packet.get("identity")
    ):
        raise ValueError("V11 P4 primary packet path or hash differs across endpoint and terminal")
    with np.load(packet_path, allow_pickle=False) as archive:
        if "__task43_record_json__" not in archive.files:
            raise ValueError("V11 P4 primary NPZ lacks its embedded raw identity")
        packet_embedded = json.loads(
            np.asarray(archive["__task43_record_json__"], dtype=np.uint8).tobytes()
        )
        packet_arrays = {
            name: np.asarray(archive[name]).copy()
            for name in archive.files
            if name != "__task43_record_json__"
        }
    embedded_identity = packet_embedded.get("identity", {})
    if (
        packet_embedded.get("schema") != "task43.v11.primary_state.v1"
        or packet_embedded.get("official_result") is not False
        or packet_embedded.get("passed") is not False
        or embedded_identity.get("phase") != "R9_H8"
        or embedded_identity.get("contract_sha256") != contract_sha256
        or embedded_identity.get("candidate_plan_sha256") != plan_sha256
        or embedded_identity.get("candidate_identity", {}).get("candidate_id")
        != "v11_r9_h8"
        or embedded_identity != packet.get("identity")
        or embedded_identity.get("source_identity") != source_identity
        or embedded_identity.get("candidate_identity") != candidate
        or embedded_identity.get("v12_recovery_binding") != recovery_binding
        or packet_embedded.get("arrays") != packet.get("arrays")
    ):
        raise ValueError("V11 P4 embedded primary packet identity differs")
    if set(packet_arrays) != set(packet_embedded.get("arrays", {})):
        raise ValueError("V11 P4 primary packet array manifest differs from its NPZ members")
    for name, values in packet_arrays.items():
        actual_array_identity = _checkpoint_array_identity(values)
        saved_array_identity = packet_embedded["arrays"].get(name, {})
        if any(
            actual_array_identity.get(key) != saved_array_identity.get(key)
            for key in ("dtype", "shape", "sha256")
        ):
            raise ValueError(f"V11 P4 primary array identity differs: {name}")
    raw_audit = record.get("primary_raw_vector_audit")
    preassembly = record.get("p4_preassembly_space_audit")
    if (
        not isinstance(raw_audit, dict)
        or raw_audit.get("pass") is not True
        or not isinstance(preassembly, dict)
        or preassembly.get("pass") is not True
    ):
        raise ValueError("V11 P4 raw-vector or preassembly space audit did not pass")
    if preassembly.get("v12_recovery_binding") != recovery_binding:
        raise ValueError("V12 P4 preassembly audit names another P2 source")
    normal_audit = embedded_identity.get("normal_correction_audit", {})
    correction_ksp = normal_audit.get("correction_ksp", {})
    storage = record.get("recovered_solution_storage", {})
    recomputed_raw = _v11_raw_vector_gates(
        packet_arrays,
        active_trace_rows=int(storage.get("active_trace_rows", -1)),
        active_interior_rows=int(storage.get("active_cell_interior_rows", -1)),
        independent_fe_dofs=int(embedded_identity.get("independent_active_fe_dofs", -1)),
        active_full_rows=int(embedded_identity.get("raw_full_active_scope", {}).get("active_full_rows", -1)),
        full_active_scope=embedded_identity.get("raw_full_active_scope", {}),
        independent_a6_scope=embedded_identity.get("independent_A6_raw_vector_scope", {}),
        normal_correction_count=int(embedded_identity.get("normal_correction_count", -1)),
        normal_converged_reason=int(correction_ksp.get("converged_reason", -1)),
        normal_correction_status=str(normal_audit.get("status", "")),
        extra_correction_count=int(embedded_identity.get("extra_correction_count", -1)),
    )
    if (
        recomputed_raw.get("pass") is not True
        or raw_audit.get("pass") is not True
        or raw_audit.get("gates") != recomputed_raw.get("gates")
    ):
        raise ValueError("V11 P4 raw-vector residual gates fail independent P5 recomputation")
    p2_audit_path = expected_plan.parent / "v11_r9_h8.audit.json"
    p2_audit = _json(p2_audit_path)
    p2_bundle = _json(Path(str(recovery_binding["bundle_path"])))
    a2_path = Path(str(recovery_binding["output_root"])) / "A2_saved_primary_q_response.json"
    a2_response = _json(a2_path)
    p2_candidates = p2_bundle.get("candidates", [])
    if (
        p2_audit.get("v12_recovery_binding") != recovery_binding
        or p2_audit.get("strict_fe_gate", {}).get("pass") is not True
        or p2_bundle.get("v12_recovery_binding") != recovery_binding
        or len(p2_candidates) != 1
        or p2_candidates[0].get("strict_fe_gate", {}).get("pass") is not True
        or a2_response.get("v12_recovery_binding") != recovery_binding
        or a2_response.get("contract_sha256") != contract_sha256
        or a2_response.get("persisted_before_space_authority") is not True
        or a2_response.get("pass") is not True
    ):
        raise ValueError("V12 P2 audit, bundle and saved A2 do not share one successful binding")
    actual = preassembly.get("actual", {})
    required_fe = contract["phases"]["P4"]["required_fe_bounds"]
    actual_fe_dofs = int(actual.get("independent_active_fe_dofs", -1))
    if not (
        actual_fe_dofs > int(required_fe["parent_fe_dofs"])
        and actual_fe_dofs < int(required_fe["target_exclusive_upper"])
    ):
        raise ValueError(
            "V11 P4 actual independent FE count is outside the strict growth bounds"
        )
    p2_match = (
        preassembly.get("pass") is True
        and preassembly.get("p2_plan_sha256") == expected_plan_sha
        and actual.get("root_cell_count") == p2_audit.get("forest", {}).get("root_cell_count")
        and actual.get("leaf_cell_count") == p2_audit.get("forest", {}).get("actual_leaf_cell_count")
        and actual.get("independent_trace_rows") == p2_audit.get("dofs", {}).get("independent_trace_rows")
        and actual.get("active_cell_interior_rows") == p2_audit.get("dofs", {}).get("active_cell_interior_rows")
        and actual.get("independent_active_fe_dofs") == p2_audit.get("dofs", {}).get("independent_active_fe_dofs")
        and actual.get("cell_interior_histogram") == p2_audit.get("degrees", {}).get("cell_interior_histogram")
        and actual.get("entity_degree_plan_sha256") == p2_audit.get("degrees", {}).get("entity_degree_plan_sha256")
        and actual.get("entity_map_sha256") == p2_audit.get("degrees", {}).get("entity_map_sha256")
        and actual.get("mesh_box_catalog_sha256") == p2_audit.get("actual_geometry", {}).get("mesh_box_catalog_sha256")
    )
    if not p2_match:
        raise ValueError("V11 P4 preassembly mesh/authority/FE differs from its saved P2 audit")
    selection_item = next(
        item for item in contract["inputs"] if item["role"] == "R9_selection_transition"
    )
    if (
        candidate.get("accepted_parent_selection_sha256") != selection_item["sha256"]
        or plan.get("task43_candidate", {}).get("provenance", {}).get("accepted_parent_selection_sha256")
        != selection_item["sha256"]
    ):
        raise ValueError("V11 P4 plan/endpoint do not retain the frozen R9 accepted parent")
    return plan_path, plan, plan_sha256


def _restore_candidate(
    candidate_run_root: Path,
    output_root: Path,
    *,
    v11_contract: dict[str, Any] | None = None,
    v11_contract_sha256: str | None = None,
    v12_recovery_binding: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record_path = candidate_run_root / "task43_round1_candidate_record.json"
    record = _json(record_path)
    if v11_contract is None:
        if record.get("schema") != "task43.round1_candidate_solve.v1":
            raise ValueError("candidate record has an unexpected schema")
        if record.get("gates", {}).get("pass") is not True:
            raise ValueError("candidate solver did not pass all hard numerical gates")
        if record.get("solver", {}).get("official_result") is not True:
            raise ValueError("candidate lacks a Task43 gated official-result identity")
    else:
        if not isinstance(v11_contract_sha256, str) or not isinstance(
            v12_recovery_binding, dict
        ):
            raise ValueError("V11 pending restore requires its frozen contract and V12 binding")
        _validate_v11_pending_candidate(
            candidate_run_root,
            record=record,
            contract=v11_contract,
            contract_sha256=v11_contract_sha256,
            recovery_binding=v12_recovery_binding,
        )

    identity = record["candidate_identity"]
    candidate_id = str(identity["candidate_id"])
    plan_path = candidate_run_root / "candidate_plan.json"
    plan_sha = _sha256_file(plan_path)
    if plan_sha != identity["plan_sha256"]:
        raise ValueError("run-local candidate plan differs from its recorded identity")
    plan = _json(plan_path)
    if plan.get("task43_candidate", {}).get("candidate_id") != candidate_id:
        raise ValueError("candidate plan identity differs from the run record")
    if _sha256_file(ACCEPTANCE) != identity["acceptance_contract_sha256"]:
        raise ValueError("frozen round-one acceptance contract changed")

    # Round-one candidates are bound to the frozen initial perturbation. Later
    # candidates are checked against an already accepted parent by the caller.
    if not identity.get("accepted_parent_selection_sha256"):
        _validate_round1_candidate_inputs(
            candidate_plan_path=plan_path,
            candidate_id=candidate_id,
            parent_run_root=CURRENT_RUN,
            tightening_run_root=ROOT / "benchmarks/artifacts/task43/current_180/tightening_attempt2/run",
            marking_record_path=ROOT / "benchmarks/artifacts/task43/current_180/tightening_marking_q8/attempt2/tightening_marking_q8.json",
            acceptance_contract_path=ACCEPTANCE,
        )

    storage_path = candidate_run_root / "candidate_recovered_solution_storage.npz"
    storage_identity = record["recovered_solution_storage"]
    if _sha256_file(storage_path) != storage_identity["sha256"]:
        raise ValueError("candidate recovered coefficient storage differs from its record")
    orders_path = candidate_run_root / "solve/dtn_port_diffraction_orders_3d.json"
    if _sha256_file(orders_path) != record["power"]["channel_rows_sha256"]:
        raise ValueError("candidate R13 modal rows differ from their record")
    mode_payload = _json(orders_path)

    cfg = _h100_config(
        kind="empty_h_active_p3",
        case_name=str(record["resolved_config"]["case_name"]),
        geometry_profile="initial_180",
    )
    cfg.stage4_local_h_refinement_plan = str(plan_path)
    mesh_data = build_stage4_local_h_mesh_data(cfg, plan_path, comm=MPI.COMM_WORLD)
    mesh = mesh_data.mesh
    axes = base._axes_from_mesh(mesh)
    actual_mesh = _assert_mesh_profile(
        mesh_data,
        axes,
        "candidate_initial180",
        candidate_plan=plan,
        candidate_plan_sha256=plan_sha,
    )
    if actual_mesh != record["numerical_controls"]["mesh"]:
        raise ValueError("rebuilt candidate mesh audit differs from the solve record")
    space = _create_nedelec_space(mesh, cfg)
    actual_arrays = base._actual_mesh_identity(mesh, space)
    expected_key_by_identity = {
        "mesh_geometry_coordinates_nm": "mesh_geometry_coordinates_nm",
        "mesh_geometry_dofmap": "mesh_geometry_dofmap",
        "mesh_owned_cell_global_ids": "mesh_owned_cell_global_ids",
        "mesh_cell_vertex_dofmap": "mesh_cell_vertex_dofmap",
        "p6_function_space_cell_dofmap": "p6_function_space_dofmap",
        "p6_owned_global_dof_block_ids": "p6_owned_global_dof_block_ids",
        "p6_ghost_global_dof_block_ids": "p6_ghost_global_dof_block_ids",
    }
    with np.load(storage_path, allow_pickle=False) as storage:
        for identity_key, storage_key in expected_key_by_identity.items():
            if not np.array_equal(actual_arrays[identity_key], storage[storage_key]):
                raise ValueError(f"candidate reconstructed {identity_key} differs from storage")
        stored_coefficients = np.asarray(
            storage["recovered_p6_local_coefficients"]
        ).copy()
        coefficients = np.asarray(stored_coefficients, dtype=np.complex128).copy()
        restoration_arrays = (
            {
                name: np.asarray(storage[name]).copy()
                for name in (*expected_key_by_identity.values(), "recovered_p6_local_coefficients")
            }
            if v11_contract is not None
            else {}
        )
    restoration_binding = None
    if v11_contract is not None:
        packet_path = candidate_run_root / "primary_state.npz"
        with np.load(packet_path, allow_pickle=False) as packet_archive:
            packet_key = "recovered_recovered_p6_local_coefficients"
            if packet_key not in packet_archive.files:
                raise ValueError("V12 P5 primary packet lacks recovered P6 coefficients")
            packet_coefficients = np.asarray(packet_archive[packet_key]).copy()
            restored_array_bindings = {}
            for name, stored_array in restoration_arrays.items():
                primary_key = "recovered_" + name
                if primary_key not in packet_archive.files:
                    raise ValueError(f"V12 P5 primary packet lacks recovery array {primary_key}")
                primary_array = np.asarray(packet_archive[primary_key])
                stored_identity = _checkpoint_array_identity(stored_array)
                primary_identity = _checkpoint_array_identity(primary_array)
                declared_identity = storage_identity.get("arrays", {}).get(name, {})
                if (
                    stored_array.dtype != primary_array.dtype
                    or stored_array.shape != primary_array.shape
                    or not np.array_equal(stored_array, primary_array)
                    or any(
                        stored_identity.get(key) != primary_identity.get(key)
                        or stored_identity.get(key) != declared_identity.get(key)
                        for key in ("dtype", "shape", "sha256")
                    )
                ):
                    raise ValueError(
                        f"V12 P5 restored coefficients or recovery indices differ from primary: {name}"
                    )
                restored_array_bindings[name] = stored_identity
        storage_coefficients_identity = _checkpoint_array_identity(
            stored_coefficients
        )
        packet_coefficients_identity = _checkpoint_array_identity(packet_coefficients)
        restoration_binding = {
            "p2_source_id": v12_recovery_binding["p2_source_id"],
            "recovery_manifest_sha256": v12_recovery_binding["manifest_sha256"],
            "primary_packet_path": str(packet_path.resolve()),
            "primary_packet_sha256": _sha256_file(packet_path),
            "primary_array_key": packet_key,
            "primary_array_identity": packet_coefficients_identity,
            "storage_path": str(storage_path.resolve()),
            "storage_sha256": _sha256_file(storage_path),
            "storage_array_identity": storage_coefficients_identity,
            "recovery_array_identities": restored_array_bindings,
            "same_array_values_dtype_and_shape": True,
        }
    field = fem.Function(space, name=f"{candidate_id}_recovered_E")
    if field.x.array.shape != coefficients.shape:
        raise ValueError("candidate full-carrier coefficients differ from reconstructed space")
    field.x.array[:] = coefficients
    field.x.scatter_forward()
    aggregate = record["power"]["aggregate"]
    power = {
        **{key: float(aggregate[key]) for key in ("R_total", "T_total", "R00_s", "R00_p", "R00_total")},
        "A_volume": float(record["power"]["A_volume_total"]),
    }
    return {
        "label": candidate_id,
        "candidate_id": candidate_id,
        "candidate_action": plan["task43_candidate"]["action"],
        "cfg": cfg,
        "mesh_data": mesh_data,
        "field": field,
        "axes": axes,
        "record": record,
        "mode_payload": mode_payload,
        "power": power,
        "mesh_identity": {name: base._array_identity(values) for name, values in actual_arrays.items()},
        "storage_sha256": storage_identity["sha256"],
        "plan_sha256": plan_sha,
        "v12_restoration_binding": restoration_binding,
    }


def _load_accepted_parent(selection_path: Path) -> dict[str, Any]:
    """Resolve an accepted parent using the shared JSON/hash identity reader."""

    return load_accepted_parent_artifacts(
        selection_path,
        artifact_root=ROOT,
        acceptance_contract_path=ACCEPTANCE,
    )


def _validate_candidate_physics(
    candidate: dict[str, Any],
    parent: dict[str, Any],
    calibration: dict[str, Any],
) -> dict[str, Any]:
    controls = candidate["record"]["numerical_controls"]
    expected_q = calibration["recorded_quadrature_and_cutoff_identity"]["expected"]
    actual_q = {
        "volume_degree": int(controls["volume_quadrature_degree"]),
        "surface_and_incident_degree": int(
            controls["incident_and_port_quadrature_degree"]
        ),
        "volume_rule": str(controls["volume_quadrature_rule"]),
        "cutoff_policy": str(controls["sparse_cutoff_policy"]),
        "cutoff_relative_tolerance": float(
            controls["sparse_cutoff_relative_tolerance"]
        ),
    }
    if actual_q != expected_q:
        raise ValueError("candidate quadrature/cutoff differs from the frozen Task43 profile")
    expected_scale = "boundary_magnitude_scaled_r5_v1"
    actual_scale = str(controls["port_amplitude_scale_policy"])
    if actual_scale != expected_scale:
        raise ValueError("candidate port amplitudes use an unexpected boundary scale")

    expected_physics = calibration["physical_configuration_identity"]["shared_identity"]
    actual_physics = base._physical_configuration_identity(candidate["cfg"])
    if actual_physics != expected_physics:
        raise ValueError("candidate resolved physical configuration differs from frozen references")
    recorded_config = candidate["record"].get("resolved_config")
    rebuilt_config = candidate["cfg"].as_jsonable()
    config_identity_keys = (
        "geometry_kind",
        "scattering_background",
        "polarization_kind",
        "electric_field_unit",
        "magnetic_field_unit",
        "lambda0",
        "period_x",
        "period_y",
        "physical_z_min",
        "physical_z_max",
        "domain_z_min",
        "domain_z_max",
        "grating_bounds",
        "interface_z",
        "air_height",
        "substrate_thickness",
        "incident_theta_deg",
        "incident_phi_deg",
        "incident_amplitude",
        "incident_e0_v_per_m",
        "n_air",
        "mu_r",
        "n_substrate",
        "n_grating",
        "eps_air",
        "eps_substrate",
        "eps_grating",
        "k0",
        "wavevector",
        "polarization",
        "magnetic_field_scale_A_per_m",
    )
    if not isinstance(recorded_config, dict) or any(
        recorded_config.get(key) != rebuilt_config.get(key)
        for key in config_identity_keys
    ):
        raise ValueError("candidate run-record config differs from its reconstructed solve config")
    cfg = candidate["cfg"]
    volume = float(cfg.period_x * cfg.period_y * (cfg.domain_z_max - cfg.domain_z_min))
    if (
        abs(complex(cfg.n_air) - 1.0) > 1.0e-14
        or abs(complex(cfg.mu_r) - 1.0) > 1.0e-14
        or abs(complex(cfg.incident_amplitude) - 1.0) > 1.0e-14
        or abs(float(cfg.incident_e0_v_per_m) - 1.0) > 1.0e-14
        or abs(volume - 350000.0) > 1.0e-8
    ):
        raise ValueError("candidate does not satisfy the fixed unit-incident field floors")

    parent_rows = parent["mode_payload"]["orders"]
    candidate_rows = candidate["mode_payload"]["orders"]
    if len(parent_rows) != 612 or len(candidate_rows) != 612:
        raise ValueError("parent or candidate modal output does not contain 612 rows")
    physical_fields = ("alpha", "gamma", "beta", "kz", "refractive_index")
    flags = ("direction", "medium", "vertical_sign", "propagating", "power_carrying")
    max_differences: dict[str, float] = {}
    for index, (parent_row, candidate_row) in enumerate(
        zip(parent_rows, candidate_rows, strict=True)
    ):
        if base._mode_key(parent_row) != base._mode_key(candidate_row):
            raise ValueError(f"candidate ordered modal key differs at row {index}")
        for name in flags:
            if parent_row[name] != candidate_row[name]:
                raise ValueError(f"candidate modal {name} differs at row {index}")
        for name in physical_fields:
            difference = float(
                np.max(
                    np.abs(
                        np.asarray(parent_row[name], dtype=np.float64)
                        - np.asarray(candidate_row[name], dtype=np.float64)
                    )
                )
            )
            max_differences[name] = max(max_differences.get(name, 0.0), difference)
            if not np.allclose(
                parent_row[name], candidate_row[name], rtol=1.0e-12, atol=1.0e-14
            ):
                raise ValueError(f"candidate modal {name} differs at row {index}")
    return {
        "resolved_physics_matches_frozen_reference_identity": True,
        "recorded_resolved_config_matches_rebuilt_config": True,
        "resolved_q_and_cutoff": actual_q,
        "boundary_amplitude_scale_policy": actual_scale,
        "unit_incident_and_volume_floor_validated": True,
        "ordered_modal_physics_fields_checked": [*physical_fields, *flags],
        "maximum_absolute_modal_parameter_differences": max_differences,
    }


def _recompute_candidate_hard_gates(
    record: dict[str, Any], mode_payload: dict[str, Any], contract: dict[str, Any],
    *, allow_legacy_initial_parent: bool = False,
) -> dict[str, Any]:
    solver = record["solver"]
    action = solver["independent_active_action"]
    a6_residual = float(action["full_solver_gauge_residual"]["raw_l2_norm"])
    independent_rhs = float(action["rhs"]["raw_l2_norm"])
    condensed = solver["condensed_residual"]
    condensed_residual = float(condensed["linear_system_residual_norm"])
    condensed_rhs = float(condensed["linear_system_rhs_norm"])
    raw_norms_valid = all(
        np.isfinite(value) and value >= 0.0
        for value in (a6_residual, independent_rhs, condensed_residual, condensed_rhs)
    )
    residual_denominators_positive = independent_rhs > 0.0 and condensed_rhs > 0.0
    a6_relative = (
        a6_residual / independent_rhs
        if raw_norms_valid and residual_denominators_positive
        else float("nan")
    )
    condensed_relative = (
        condensed_residual / condensed_rhs
        if raw_norms_valid and residual_denominators_positive
        else float("nan")
    )
    power = record["power"]
    aggregate = power["aggregate"]
    a_volume = float(power["A_volume_total"])
    r_total = float(aggregate["R_total"])
    t_total = float(aggregate["T_total"])
    energy_closure = abs(1.0 - r_total - t_total - a_volume)

    rows = mode_payload.get("orders")
    if not isinstance(rows, list) or len(rows) != 612:
        raise ValueError("candidate output inventory is not exactly 612 ordered modes")
    keys = [base._mode_key(row) for row in rows]
    if len(set(keys)) != 612:
        raise ValueError("candidate output inventory contains duplicate modal identities")
    finite_inventory = True
    for row in rows:
        numeric_values = [row.get(key) for key in ("power_ratio", "R", "T")]
        numeric_values.extend(
            row.get(key, ())
            for key in ("outgoing_amplitude_at_boundary", "alpha", "gamma", "beta", "kz", "refractive_index")
        )
        try:
            finite_inventory = finite_inventory and all(
                np.isfinite(np.asarray(value, dtype=np.float64)).all()
                for value in numeric_values
            )
        except (TypeError, ValueError):
            finite_inventory = False

    storage = record["recovered_solution_storage"]
    trace_rows = int(storage["active_trace_rows"])
    interior_rows = int(storage["active_cell_interior_rows"])
    independent_dofs = trace_rows + interior_rows
    storage_declared_dofs = storage.get("independent_active_fe_dofs")
    active_space = record.get("numerical_controls", {}).get("active_space") or {}
    summary_declared_dofs = active_space.get("independent_active_fe_dofs")
    dof_declarations_match = (
        storage_declared_dofs is not None
        and summary_declared_dofs is not None
        and int(storage_declared_dofs) == independent_dofs
        and int(summary_declared_dofs) == independent_dofs
    )
    residual_groups = action["groups"]
    dof_row_counts_match = (
        trace_rows == int(residual_groups["independent_active_trace_residual"]["row_count"])
        and interior_rows
        == int(residual_groups["independent_active_interior_residual"]["row_count"])
    )
    # The frozen initial record predates the two duplicate FE declarations.
    # Only its explicit parent role may use the original raw row identities.
    legacy_initial_identity = (
        allow_legacy_initial_parent
        and record.get("schema") == "task43.initial_180_cell_active_p3_current.v1"
        and record.get("case_id") == "current_active_p3_initial180_mpi1"
        and "independent_active_fe_dofs" not in storage
        and "active_space" not in record.get("numerical_controls", {})
        and trace_rows == 8640 and interior_rows == 6480
        and independent_dofs == 15120
        and action.get("rows") == {
            "independent_trace": 8640, "active_cell_interior": 6480,
            "modal_lower": 612,
        }
        and dof_row_counts_match
    )
    hard_limits = contract["final_tolerances"]
    mesh_audit_pass = (
        record["numerical_controls"].get("local_h_actual_audit", {}).get("pass") is True
    )
    raw_checks = {
        "residual_norms_are_finite_and_nonnegative": raw_norms_valid,
        "residual_denominators_are_positive": residual_denominators_positive,
        "independent_A6_le_1e-6": bool(
            np.isfinite(a6_relative)
            and a6_relative <= float(hard_limits["independent_full_active_relative_residual"])
        ),
        "condensed_residual_le_1e-9": bool(
            np.isfinite(condensed_relative)
            and condensed_relative <= float(hard_limits["condensed_direct_relative_residual"])
        ),
        "energy_closure_le_1e-5": bool(
            np.isfinite(energy_closure)
            and energy_closure
            <= float(hard_limits["absolute_energy_closure_1_minus_R_minus_T_minus_A_volume"])
        ),
        "finite_unique_612_mode_inventory": bool(finite_inventory and len(set(keys)) == 612),
        "independent_dofs_match_residual_rows": bool(
            independent_dofs > 0 and dof_row_counts_match
        ),
        ("legacy_initial_parent_raw_FE_identity_matches"
         if legacy_initial_identity
         else "independent_dofs_match_both_record_declarations"): (
            legacy_initial_identity or dof_declarations_match
        ),
        "actual_mesh_and_closure_audit_pass": mesh_audit_pass,
        "recorded_gate_and_official_identity_pass": bool(
            record.get("gates", {}).get("pass") is True
            and record.get("solver", {}).get("official_result") is True
        ),
    }
    return {
        "classification": "checker_recomputed_from_raw_record_fields",
        "independent_A6": {
            "residual_raw_l2_norm": a6_residual,
            "independent_rhs_raw_l2_norm": independent_rhs,
            "relative": a6_relative,
        },
        "condensed_residual": {
            "residual_raw_l2_norm": condensed_residual,
            "rhs_raw_l2_norm": condensed_rhs,
            "relative": condensed_relative,
        },
        "energy_closure": {
            "R_total": r_total,
            "T_total": t_total,
            "A_volume": a_volume,
            "absolute_1_minus_R_minus_T_minus_A": energy_closure,
        },
        "channel_inventory": {
            "row_count": len(rows),
            "unique_key_count": len(set(keys)),
            "all_numeric_outputs_finite": bool(finite_inventory),
        },
        "actual_space": {
            "independent_trace_rows": trace_rows,
            "active_cell_interior_rows": interior_rows,
            "independent_FE_dofs": independent_dofs,
            "storage_declared_independent_FE_dofs": storage_declared_dofs,
            "active_space_declared_independent_FE_dofs": summary_declared_dofs,
            "both_declarations_match_recomputed_sum": dof_declarations_match,
            "declaration_validation_route": (
                "explicit_legacy_initial_parent_storage_and_A6_rows"
                if legacy_initial_identity else "both_record_declarations_required"
            ),
            "residual_row_counts_match": dof_row_counts_match,
        },
        "hard_checks": raw_checks,
        "pass": all(raw_checks.values()),
    }


def _axes_subset(
    candidate_axes: tuple[np.ndarray, ...], common_axes: tuple[np.ndarray, ...]
) -> bool:
    for candidate, common in zip(candidate_axes, common_axes, strict=True):
        for value in candidate:
            index = int(np.searchsorted(common, value))
            neighbors = [slot for slot in (index - 1, index) if 0 <= slot < common.size]
            if not neighbors or min(abs(float(common[slot]) - float(value)) for slot in neighbors) > 1.0e-12:
                return False
    return True


def _sample_field(case: dict[str, Any], points: np.ndarray) -> dict[str, np.ndarray]:
    export = prepare_cell_local_vector_field_export(case["field"])
    values = sample_cell_local_vector_fields(
        {"E": export.electric_dgq6, "curl_E": export.curl_electric_dgq6},
        points,
        batch_size=32768,
    )
    if values is None:
        raise RuntimeError("MPI1 field sampler returned no samples")
    return values


def _j_infinity(
    modal: dict[str, Any], field_metrics: dict[str, Any]
) -> dict[str, Any]:
    scaled: dict[str, float] = {}
    tolerances = {
        "R_total": 1.0e-5,
        "T_total": 1.0e-5,
        "A_volume": 1.0e-5,
        "R00_s": 1.0e-6,
        "R00_p": 1.0e-6,
        "R00_total": 1.0e-5,
    }
    for key, tolerance in tolerances.items():
        scaled[f"power.{key}"] = abs(float(modal["power_absolute_differences"][key])) / tolerance
    scaled["power.max_individual_channel"] = (
        float(modal["maximum_individual_channel_power_ratio_absolute_difference"]) / 1.0e-6
    )
    for group, values in modal["boundary_amplitude_groups"].items():
        scaled[f"amplitude.{group}"] = float(values["relative_with_unit_incident_modal_floor"]) / 1.0e-4
    for name in (
        "E_total_code",
        "H_total_A_per_m",
        "E_scattered_code",
        "H_scattered_A_per_m",
    ):
        scaled[f"field.{name}"] = float(
            field_metrics[name]["relative_to_reference_or_floor"]
        ) / 1.0e-4
    scaled["field.G"] = float(
        field_metrics["G"]["relative_with_incident_floor"]
    ) / 1.0e-4
    if not scaled or not all(np.isfinite(value) for value in scaled.values()):
        raise ValueError("J_infinity contains non-finite observable components")
    witness = max(scaled, key=scaled.__getitem__)
    return {"value": scaled[witness], "witness": witness, "components": scaled}


def compare_candidate(
    candidate_run_root: Path,
    output_root: Path,
    parent_selection_path: Path | None = None,
) -> dict[str, Any]:
    if MPI.COMM_WORLD.size != 1:
        raise RuntimeError("round-one candidate comparison currently requires MPI1")
    if output_root.exists():
        raise FileExistsError(f"refusing to overwrite comparison attempt {output_root}")
    output_root.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    source_start = base._source_snapshot()
    source_start["candidate_comparator_sha256"] = _sha256_file(Path(__file__))
    source_start["candidate_records_sha256"] = _sha256_file(CANDIDATE_RECORDS)
    (output_root / "source_identity_start.json").write_text(
        json.dumps(source_start, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    contract = _json(ACCEPTANCE)
    comparison_contract_path = ROOT / contract["evidence"]["comparison_contract"]["path"]
    calibration_path = ROOT / contract["evidence"]["reference_and_quadrature"]["path"]
    if _sha256_file(comparison_contract_path) != contract["evidence"][
        "comparison_contract"
    ]["sha256"]:
        raise ValueError("frozen comparison contract differs from round-one acceptance")
    if _sha256_file(calibration_path) != contract["evidence"][
        "reference_and_quadrature"
    ]["sha256"]:
        raise ValueError("reference calibration differs from round-one acceptance")
    comparison_contract = _json(comparison_contract_path)
    calibration_record = _json(calibration_path)
    if (
        calibration_record.get("status")
        != "REFERENCE_PAIR_FIELD_AND_MODAL_COMPARISON_COMPLETE_CANDIDATE_RUNS_PENDING"
        or calibration_record.get("reference_roles")
        != {"selection": "Y6_1", "calibration": "Y6_2", "holdout": "Y5_1_not_read"}
        or calibration_record.get("source_identity", {}).get(
            "unchanged_during_comparison"
        )
        is not True
    ):
        raise ValueError("frozen reference calibration is not a complete, source-stable pair")
    accepted_parent = (
        None if parent_selection_path is None else _load_accepted_parent(parent_selection_path)
    )
    if accepted_parent is None:
        parent_modal = _load_modal_case("current_180")
    else:
        parent_record = accepted_parent["record"]
        parent_orders_path = accepted_parent["run_root"] / "solve/dtn_port_diffraction_orders_3d.json"
        if _sha256_file(parent_orders_path) != parent_record["power"]["channel_rows_sha256"]:
            raise ValueError("accepted parent modal rows differ from their record")
        parent_modal = {"record": parent_record, "mode_payload": _json(parent_orders_path)}
    parent_gate_recalculation = _recompute_candidate_hard_gates(
        parent_modal["record"], parent_modal["mode_payload"], comparison_contract,
        allow_legacy_initial_parent=accepted_parent is None,
    )
    (output_root / "parent_raw_hard_gate_precheck.json").write_text(
        json.dumps(parent_gate_recalculation, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if not parent_gate_recalculation["pass"]:
        raise ValueError("comparison parent fails raw hard-gate recalculation")
    candidate = _restore_candidate(candidate_run_root, output_root)
    has_accepted_parent_binding = bool(
        candidate["record"].get("candidate_identity", {}).get(
            "accepted_parent_selection_sha256"
        )
    )
    if has_accepted_parent_binding != (parent_selection_path is not None):
        raise ValueError(
            "candidate parent-selection binding and comparator parent argument disagree"
        )
    if accepted_parent is not None:
        candidate_plan = _json(candidate_run_root / "candidate_plan.json")
        provenance = candidate_plan.get("task43_candidate", {}).get("provenance", {})
        parent_hashes = accepted_parent["hashes"]
        expected_parent_identity = {
            "accepted_parent_selection_sha256": accepted_parent["selection_sha256"],
            "parent_run_root": str(accepted_parent["run_root"]),
            "parent_candidate_id": accepted_parent["selected"]["candidate_id"],
            "parent_case_record_sha256": parent_hashes["record_sha256"],
            "parent_recovered_storage_sha256": parent_hashes["storage_sha256"],
            "parent_plan_sha256": parent_hashes["plan_sha256"],
            "parent_comparison_sha256": parent_hashes["comparison_record_sha256"],
            "acceptance_contract_sha256": _sha256_file(ACCEPTANCE),
        }
        if any(provenance.get(key) != value for key, value in expected_parent_identity.items()):
            raise ValueError("candidate plan is not bound to the accepted parent artifacts")
        if Path(str(provenance.get("accepted_parent_selection_record_path"))).resolve() != accepted_parent["selection_path"]:
            raise ValueError("candidate plan names a different accepted selection record")
        candidate_identity = candidate["record"].get("candidate_identity", {})
        if (
        candidate_identity.get("accepted_parent_selection_sha256")
            != accepted_parent["selection_sha256"]
            or candidate_identity.get("parent_candidate_id")
            != accepted_parent["selected"]["candidate_id"]
        ):
            raise ValueError("candidate solve record is not bound to the accepted parent selection")
    if accepted_parent is None:
        parent_candidate = None
        parent_label = "current_180"
    else:
        parent_candidate = _restore_candidate(
            accepted_parent["run_root"], output_root / "accepted_parent_restore"
        )
        if parent_candidate["candidate_id"] != accepted_parent["selected"]["candidate_id"]:
            raise ValueError("restored parent candidate differs from accepted selection")
        parent_modal = {
            "label": parent_candidate["candidate_id"],
            "record": parent_candidate["record"],
            "mode_payload": parent_candidate["mode_payload"],
            "power": parent_candidate["power"],
        }
        parent_label = parent_candidate["candidate_id"]
    selection_modal = _load_modal_case("Y6_1")
    calibration_modal = _load_modal_case("Y6_2")
    calibration_mode_validation = base._validate_mode_physics(
        {
            "current_180": {**parent_modal, "label": "current_180"},
            "Y6_1": selection_modal,
            "Y6_2": calibration_modal,
        }
    )
    calibration_q_validation = base._validate_recorded_quadrature_and_cutoff(
        {
            "current_180": {**parent_modal, "label": "current_180"},
            "Y6_1": selection_modal,
            "Y6_2": calibration_modal,
        }
    )
    candidate_physics_validation = _validate_candidate_physics(
        candidate, parent_modal, calibration_record
    )
    candidate_gate_recalculation = _recompute_candidate_hard_gates(
        candidate["record"], candidate["mode_payload"], comparison_contract
    )
    q8_identity = calibration_record["quadrature"]["q8"]
    cached_samples_path = Path(q8_identity["sample_bundle"])
    if not cached_samples_path.is_absolute():
        cached_samples_path = ROOT / cached_samples_path
    if _sha256_file(cached_samples_path) != q8_identity["sample_bundle_sha256"]:
        raise ValueError("frozen q8 reference sample bundle differs from its record")
    with np.load(cached_samples_path, allow_pickle=False) as archive:
        cached = {key: np.asarray(archive[key]).copy() for key in archive.files}
    cached_axes = tuple(
        np.asarray(axis, dtype=np.float64)
        for axis in q8_identity["axis_breakpoints_nm"]
    )
    cached_rule = build_common_volume_quadrature([cached_axes], gauss_order=8)
    if cached_rule.rule_sha256 != q8_identity["rule_sha256"]:
        raise ValueError("cached q8 points do not match the frozen quadrature identity")
    if not np.array_equal(cached_rule.points_nm, cached["points_nm"]) or not np.array_equal(
        cached_rule.weights_nm3, cached["weights_nm3"]
    ):
        raise ValueError("cached q8 sample coordinates/weights differ from regenerated rule")

    reuse_cached = _axes_subset(candidate["axes"], cached_axes) and (
        parent_candidate is None or _axes_subset(parent_candidate["axes"], cached_axes)
    )
    cases: dict[str, dict[str, Any]] = {}
    if reuse_cached:
        quadrature = cached_rule
        parent_samples = (
            {"E": cached["current_180_E_code"], "curl_E": cached["current_180_curl_E_code"]}
            if parent_candidate is None
            else _sample_field(parent_candidate, quadrature.points_nm)
        )
        sampled = {
            parent_label: parent_samples,
            "Y6_1": {"E": cached["Y6_1_E_code"], "curl_E": cached["Y6_1_curl_E_code"]},
        }
    else:
        cases = {"Y6_1": _restore_case_fields("Y6_1", output_root)}
        if parent_candidate is None:
            cases["current_180"] = _restore_case_fields("current_180", output_root)
            parent_case = cases["current_180"]
        else:
            parent_case = parent_candidate
        # The frozen q8 axes include both reference meshes; add actual parent
        # and candidate leaf boundaries, then resample only Y6_1 and the parent.
        axes_to_merge = [cached_axes]
        axes_to_merge.extend((parent_case["axes"], cases["Y6_1"]["axes"]))
        axes_to_merge.append(candidate["axes"])
        quadrature = build_common_volume_quadrature(axes_to_merge, gauss_order=8)
        sampled = {"Y6_1": _sample_field(cases["Y6_1"], quadrature.points_nm)}
        sampled[parent_label] = _sample_field(parent_case, quadrature.points_nm)

    candidate_samples = _sample_field(candidate, quadrature.points_nm)
    sampled[candidate["label"]] = candidate_samples
    if parent_candidate is not None:
        cfg = parent_candidate["cfg"]
    elif "current_180" not in cases:
        current_record = parent_modal["record"]
        cfg = _h100_config(
            kind="empty_h_active_p3",
            case_name=str(current_record["resolved_config"]["case_name"]),
            geometry_profile="initial_180",
        )
    else:
        cfg = cases["current_180"]["cfg"]
    parent_modal_case = {**parent_modal, "label": parent_label}
    reference_modal_case = {**selection_modal, "label": "Y6_1"}
    candidate_modal_case = {**candidate, "label": candidate["candidate_id"]}
    parent_modal_metrics = base._modal_comparison(reference_modal_case, parent_modal_case)
    candidate_modal_metrics = base._modal_comparison(reference_modal_case, candidate_modal_case)
    parent_field_metrics = base._field_metrics(
        sampled["Y6_1"], sampled[parent_label], quadrature.points_nm,
        quadrature.weights_nm3, cfg,
    )
    candidate_field_metrics = base._field_metrics(
        sampled["Y6_1"], candidate_samples, quadrature.points_nm,
        quadrature.weights_nm3, cfg,
    )
    parent_j = _j_infinity(parent_modal_metrics, parent_field_metrics)
    candidate_j = _j_infinity(candidate_modal_metrics, candidate_field_metrics)

    candidate_global_ids, candidate_point_slots = base._cell_slot_for_points(
        candidate["mesh_data"].mesh,
        candidate["axes"],
        quadrature.points_nm,
    )
    contributions = accumulate_physical_g_cell_contributions(
        sampled["Y6_1"]["E"], candidate_samples["E"],
        sampled["Y6_1"]["curl_E"], candidate_samples["curl_E"],
        quadrature.weights_nm3, candidate_point_slots,
        cell_global_ids=candidate_global_ids,
        k0_per_nm=float(cfg.k0),
    )
    marked_ids, marking = dorfler_mark_physical_g(
        candidate_global_ids, contributions, theta=0.5
    )
    contribution_sum = float(np.sum(contributions, dtype=np.float64))
    expected_difference_squared = float(
        candidate_field_metrics["G"]["difference_g_norm"]
    ) ** 2
    contribution_closure = abs(contribution_sum - expected_difference_squared) / max(
        expected_difference_squared, 1.0e-300
    )
    if contribution_closure > 2.0e-12:
        raise ValueError("candidate leaf G contributions do not close to the full-volume metric")

    eta_parent = float(parent_field_metrics["G"]["relative_with_incident_floor"])
    eta_candidate = float(candidate_field_metrics["G"]["relative_with_incident_floor"])
    epsilon_g = float(contract["acceptance"]["epsilon_G"])
    epsilon_j = float(contract["acceptance"]["epsilon_J"])
    parent_dofs = int(parent_gate_recalculation["actual_space"]["independent_FE_dofs"])
    candidate_dofs = int(
        candidate_gate_recalculation["actual_space"]["independent_FE_dofs"]
    )
    dof_increment = candidate_dofs - parent_dofs
    g_improvement = eta_parent - eta_candidate
    gates = {
        "candidate_solver_hard_gates_pass": candidate_gate_recalculation["pass"],
        "positive_actual_independent_dof_increment": dof_increment > 0,
        "G_decrease_exceeds_frozen_noise": g_improvement > epsilon_g,
        "J_infinity_within_frozen_noise": candidate_j["value"] <= parent_j["value"] + epsilon_j,
    }
    gates["pass"] = all(gates.values())

    sample_path = output_root / (
        "round1_candidate_shared_volume_q8.npz"
        if accepted_parent is None
        else "candidate_shared_volume_q8.npz"
    )
    sample_arrays = {
        "points_nm": quadrature.points_nm,
        "weights_nm3": quadrature.weights_nm3,
        "candidate_cell_global_ids": candidate_global_ids,
        "point_candidate_cell_local_slots": candidate_point_slots,
    }
    for label, values in sampled.items():
        sample_arrays[f"{label}_E_code"] = values["E"]
        sample_arrays[f"{label}_curl_E_code"] = values["curl_E"]
    np.savez_compressed(sample_path, **sample_arrays)

    source_end = base._source_snapshot()
    source_end["candidate_comparator_sha256"] = _sha256_file(Path(__file__))
    source_end["candidate_records_sha256"] = _sha256_file(CANDIDATE_RECORDS)
    sources_unchanged = bool(
        source_start["git_head"] == source_end["git_head"]
        and source_start["file_sha256"] == source_end["file_sha256"]
        and source_start["candidate_comparator_sha256"]
        == source_end["candidate_comparator_sha256"]
        and source_start["candidate_records_sha256"]
        == source_end["candidate_records_sha256"]
    )
    if not sources_unchanged:
        raise RuntimeError("comparison source identity changed during candidate postprocessing")
    record = {
        "schema": "task43.round1-candidate-comparison.v1",
        "classification": "measured_candidate_against_frozen_selection_reference_and_acceptance_contract",
        "candidate_id": candidate["candidate_id"],
        "candidate_action": candidate["candidate_action"],
        "candidate_run_root": str(candidate_run_root.resolve()),
        "candidate_record_sha256": _sha256_file(candidate_run_root / "task43_round1_candidate_record.json"),
        "candidate_storage_sha256": candidate["storage_sha256"],
        "candidate_plan_sha256": candidate["plan_sha256"],
        "selection_reference": "Y6_1",
        "calibration_reference": "Y6_2",
        "holdout_read": False,
        "final_p6_control_read": False,
        "verified_source_contracts": {
            "round1_acceptance_contract_sha256": _sha256_file(ACCEPTANCE),
            "comparison_contract_sha256": _sha256_file(comparison_contract_path),
            "reference_calibration_sha256": _sha256_file(calibration_path),
            "reference_mode_physics_validation": calibration_mode_validation,
            "reference_q_and_cutoff_validation": calibration_q_validation,
            "candidate_physics_validation": candidate_physics_validation,
            "candidate_raw_hard_gate_recalculation": candidate_gate_recalculation,
            "parent_raw_hard_gate_recalculation": parent_gate_recalculation,
        },
        "parent_identity": (
            None
            if accepted_parent is None
            else {
                "selection_record_path": str(accepted_parent["selection_path"]),
                "selection_record_sha256": accepted_parent["selection_sha256"],
                "candidate_id": accepted_parent["selected"]["candidate_id"],
                "run_root": str(accepted_parent["run_root"]),
                **accepted_parent["hashes"],
            }
        ),
        "q8": {
            "rule_sha256": quadrature.rule_sha256,
            "axis_breakpoints_nm": [axis.tolist() for axis in quadrature.axis_breakpoints_nm],
            "sample_count": quadrature.point_count,
            "reused_frozen_reference_rule_and_selection_samples": reuse_cached,
            "sample_bundle": str(sample_path),
            "sample_bundle_sha256": _sha256_file(sample_path),
            "integrated_domain_volume_nm3": float(np.sum(quadrature.weights_nm3)),
        },
        "field_metrics_vs_selection_reference": {
            "parent": parent_field_metrics,
            "candidate": candidate_field_metrics,
        },
        "modal_and_power_metrics_vs_selection_reference": {
            "parent": parent_modal_metrics,
            "candidate": candidate_modal_metrics,
        },
        "J_infinity": {
            "parent": parent_j,
            "candidate": candidate_j,
            "epsilon_J": epsilon_j,
        },
        "selection": {
            "eta_parent": eta_parent,
            "eta_candidate": eta_candidate,
            "G_improvement": g_improvement,
            "epsilon_G": epsilon_g,
            "parent_independent_FE_dofs": parent_dofs,
            "candidate_independent_FE_dofs": candidate_dofs,
            "actual_added_independent_FE_dofs": dof_increment,
            "primary_score_G_improvement_per_added_independent_FE_dof": (
                g_improvement / dof_increment if dof_increment > 0 else None
            ),
            "primary_score_noise_half_width": (
                epsilon_g / dof_increment if dof_increment > 0 else None
            ),
            "primary_score_noise_interval": (
                {
                    "lower": (g_improvement - epsilon_g) / dof_increment,
                    "upper": (g_improvement + epsilon_g) / dof_increment,
                    "half_width": epsilon_g / dof_increment,
                    "formula": "(eta_parent - eta_candidate +/- epsilon_G) / actual_added_independent_FE_dofs",
                }
                if dof_increment > 0
                else None
            ),
            "gates": gates,
            "status": "eligible_under_frozen_acceptance_contract" if gates["pass"] else "rejected_under_frozen_acceptance_contract",
        },
        "candidate_leaf_G_contributions": {
            "cell_global_ids": candidate_global_ids.tolist(),
            "cell_g_error_squared": contributions.tolist(),
            "marked_global_cell_ids": marked_ids.tolist(),
            "marking": marking,
            "sum_vs_full_volume_g_difference_relative_closure": contribution_closure,
        },
        "source_identity_start": source_start,
        "source_identity_end": source_end,
        "sources_unchanged_during_comparison": sources_unchanged,
        "wall_seconds": time.perf_counter() - started,
    }
    output_name = (
        "round1_candidate_comparison_v1.json"
        if accepted_parent is None
        else "candidate_comparison_v2.json"
    )
    record["schema"] = (
        "task43.round1-candidate-comparison.v1"
        if accepted_parent is None
        else "task43.candidate-comparison.v2"
    )
    record["parent_candidate_id"] = None if accepted_parent is None else parent_label
    output_path = output_root / output_name
    output_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "stage": "candidate_comparison_complete",
                "candidate_id": candidate["candidate_id"],
                "status": record["selection"]["status"],
                "eta_candidate": eta_candidate,
                "J_candidate": candidate_j["value"],
                "record": str(output_path),
                "wall_seconds": record["wall_seconds"],
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return record


def _post_selection_full_mode_physics(case: dict[str, Any]) -> dict[str, Any]:
    """Re-evaluate all saved612 modal rows with the existing physical helpers."""
    modes = tuple(outgoing_port_modes_3d(case["cfg"]))
    rows = case["mode_payload"]["orders"]
    if len(modes) != 612 or len(rows) != 612:
        raise ValueError("post-selection mode checker requires full612")
    expected = {"mode_payload": {"orders": [
        {**_mode_identity(mode), "kz": base._complex_components(mode.k_vector[2]),
         "direction": "outgoing_up" if mode.side == "top" else "outgoing_down",
         "medium": "air" if mode.side == "top" else "substrate",
         "power_carrying": _mode_carries_outward_power(mode)} for mode in modes]}}
    physics = base._validate_mode_physics(
        {"expected": expected, "actual": case}, labels=("expected", "actual"))
    incident = float(incident_power_3d(case["cfg"]))
    if not np.isfinite(incident) or incident <= 0.0:
        raise ValueError("post-selection incident power must be finite positive")
    recomputed = []
    boundary_errors = []
    sums = {key: 0.0 for key in ("R_total", "T_total", "R00_s", "R00_p")}
    for mode, row in zip(modes, rows, strict=True):
        outgoing = base._complex_pair(row["outgoing_amplitude"])
        boundary = outgoing * _mode_boundary_phase(mode, case["cfg"])
        archived_boundary = base._complex_pair(row["outgoing_amplitude_at_boundary"])
        if not np.isclose(boundary, archived_boundary, rtol=1e-12, atol=1e-14):
            raise ValueError("post-selection raw boundary amplitude differs from physical basis conversion")
        boundary_errors.append(float(abs(boundary - archived_boundary)))
        power = float(_mode_power_at_boundary(mode, case["cfg"], outgoing) / incident)
        if not np.isfinite(power) or not np.isclose(power, row["power_ratio"], rtol=1e-12, atol=1e-14):
            raise ValueError("post-selection raw mode power differs from physical mode power")
        r = power if mode.side == "top" and _mode_carries_outward_power(mode) else 0.0
        t = power if mode.side == "bottom" and _mode_carries_outward_power(mode) else 0.0
        if not np.isclose(r, row["R"], rtol=1e-12, atol=1e-14) or not np.isclose(t, row["T"], rtol=1e-12, atol=1e-14):
            raise ValueError("post-selection raw row R/T differs from recomputed side power")
        recomputed.append(power)
        sums["R_total"] += r
        sums["T_total"] += t
        if mode.side == "top" and mode.m == 0 and mode.n == 0:
            sums[f"R00_{mode.polarization}"] += r
    sums["R00_total"] = sums["R00_s"] + sums["R00_p"]
    if any(not np.isclose(value, case["power"][name], rtol=1e-12, atol=1e-14) for name, value in sums.items()):
        raise ValueError("post-selection recomputed full mode sums differ from aggregate")
    return {"physical_mode_identity": physics, "incident_power": incident,
            "recomputed_all612_power_ratios": recomputed,
            "boundary_amplitude_absolute_differences": boundary_errors,
            "recomputed_power_sums": sums, "rtol": 1e-12, "atol": 1e-14,
            "scope": "Actual historical-unscaled or Task43-scaled cfg; existing physical mode, phase and power functions; no phase fit"}


def _v11_fixed_h_classification(
    *, j_r9: float, j_h: float, eta_r9: float, eta_h: float,
    epsilon_j: float, epsilon_g: float,
) -> dict[str, Any]:
    if not all(np.isfinite(value) for value in (j_r9, j_h, eta_r9, eta_h)):
        raise ValueError("V11 fixed-h classification metrics must all be finite")
    delta_j = j_r9 - j_h
    delta_g = eta_r9 - eta_h
    if delta_j > epsilon_j and eta_h <= eta_r9 + epsilon_g:
        classification = "POSITIVE_FIXED_REFERENCE_OUTPUT_RESPONSE"
    elif j_h > j_r9 + epsilon_j or eta_h > eta_r9 + epsilon_g:
        classification = "NEGATIVE_OR_TRADEOFF_RESPONSE"
    else:
        classification = "NO_CLEAR_OUTPUT_GAIN_AT_FROZEN_SCALE"
    return {
        "classification": classification,
        "Delta_J": delta_j,
        "Delta_G": delta_g,
        "positive_condition_pass": bool(
            delta_j > epsilon_j and eta_h <= eta_r9 + epsilon_g
        ),
        "negative_or_tradeoff_condition_pass": bool(
            j_h > j_r9 + epsilon_j or eta_h > eta_r9 + epsilon_g
        ),
        "legacy_double_gate_pass": bool(
            delta_g > epsilon_g and j_h <= j_r9 + epsilon_j
        ),
        "selection_transition_written": False,
    }


def _v11_signed_mode_differences(
    reference: dict[str, Any], candidate: dict[str, Any]
) -> dict[str, Any]:
    reference_keys, reference_amplitudes, reference_rows = base._modal_identity(
        reference["mode_payload"], reference["label"]
    )
    candidate_keys, candidate_amplitudes, candidate_rows = base._modal_identity(
        candidate["mode_payload"], candidate["label"]
    )
    if reference_keys != candidate_keys or len(reference_keys) != 612:
        raise ValueError("V11 signed modal deltas require matching ordered R13 rows")
    signed_power = [
        float(candidate_row["power_ratio"]) - float(reference_row["power_ratio"])
        for reference_row, candidate_row in zip(reference_rows, candidate_rows, strict=True)
    ]
    amplitude_delta = candidate_amplitudes - reference_amplitudes
    return {
        "aggregate_signed_candidate_minus_reference": {
            key: float(candidate["power"][key]) - float(reference["power"][key])
            for key in ("R_total", "T_total", "A_volume", "R00_s", "R00_p", "R00_total")
        },
        "signed_individual_channel_power_ratio_differences": [
            {"mode_key": list(key), "candidate_minus_reference": value}
            for key, value in zip(reference_keys, signed_power, strict=True)
        ],
        "complex_boundary_amplitude_differences": [
            {
                "mode_key": list(key),
                "candidate_minus_reference": [float(delta.real), float(delta.imag)],
            }
            for key, delta in zip(reference_keys, amplitude_delta, strict=True)
        ],
        "maximum_absolute_complex_boundary_amplitude_difference": float(
            np.max(np.abs(amplitude_delta))
        ),
    }


def compare_v11_union(
    candidate_run_root: Path,
    accepted_parent_selection_record: Path,
    *,
    contract_path: Path,
    recovery_manifest_path: Path,
    attempt_id: str,
    saved_primary_recovery_binding_path: Path | None = None,
) -> dict[str, Any]:
    """Restore R9, pending V11 h and Y6_1; sample one common q8/q10 union."""
    if MPI.COMM_WORLD.size != 1:
        raise RuntimeError("V11 P5 union comparison is fixed to MPI1")
    contract, contract_sha256 = _load_v11_primary_contract(contract_path)
    recovery = _load_v12_execution_recovery_manifest(
        recovery_manifest_path,
        contract_sha256=contract_sha256,
    )
    phase = contract["phases"]["P5"]
    if attempt_id != "v11_r9_h8_union_attempt1":
        raise ValueError("V11 P5 requires its one frozen support attempt id")
    expected_candidate_root = (
        Path(str(contract["artifact_prefix"]))
        / str(contract["phases"]["P4"]["root"])
        / "run"
    ).resolve()
    if candidate_run_root.resolve() != expected_candidate_root:
        raise ValueError("V11 P5 candidate root differs from the unique P4 run")
    saved_primary_mode = saved_primary_recovery_binding_path is not None
    terminal_path = candidate_run_root / (
        "task43_v11_partial_terminal.json"
        if saved_primary_mode
        else "task43_v11_primary_terminal.json"
    )
    # Freeze the terminal bytes before inspecting its selected P2 plan path.
    terminal_sha256_before = _sha256_file(terminal_path)
    terminal = _json(terminal_path)
    terminal_binding = terminal.get("v12_recovery_binding")
    if not isinstance(terminal_binding, dict):
        raise ValueError("V12 P5 P4 terminal has no explicit P2 source binding")
    p2_source = _resolve_v12_p2_source(
        recovery,
        candidate_plan_path=Path(str(terminal_binding.get("plan_output_path", ""))),
    )
    recovery_binding = {
        "manifest_path": recovery["manifest_path"],
        "manifest_sha256": recovery["manifest_sha256"],
        "contract_sha256": contract_sha256,
        "p2_source_id": p2_source["p2_source_id"],
        "support_root": p2_source["support_root"],
        "output_root": p2_source["output_root"],
        "plan_output_path": p2_source["plan_output_path"],
        "audit_path": p2_source["audit_path"],
        "bundle_path": p2_source["bundle_path"],
    }
    for key in (
        "user_recovery_authorization_path",
        "user_recovery_authorization_sha256",
        "superseded_failure_closeout_path",
        "superseded_failure_closeout_sha256",
    ):
        if key in p2_source:
            recovery_binding[key] = p2_source[key]
    saved_primary_binding = None
    if saved_primary_mode:
        if terminal.get("status") != "FAILED":
            raise ValueError("V15 saved-primary P5 requires the original FAILED P4 terminal")
        if terminal_binding != recovery_binding:
            raise ValueError("V15 saved-primary P4 source differs from the recovery manifest")
        (
            saved_primary_binding,
            v12_inputs_before,
            terminal,
        ) = _v15_h_saved_primary_binding_and_inputs(
            candidate_run_root,
            binding_path=saved_primary_recovery_binding_path,
            contract_sha256=contract_sha256,
            recovery_binding=recovery_binding,
        )
        if saved_primary_binding.get("output_root") != str(
            (
                Path(str(contract["artifact_prefix"]))
                / str(phase["comparison_output_root"])
                / "saved_primary_recovery"
            ).resolve()
        ):
            raise ValueError("V15 saved-primary recovery output is not its fixed P5 child")
    else:
        if terminal_binding != recovery_binding:
            raise ValueError("V12 P5 terminal source id/path differs from its recovery manifest")
        v12_inputs_before = _v12_p5_input_snapshot(
            candidate_run_root,
            contract_sha256=contract_sha256,
            recovery_binding=recovery_binding,
        )
    terminal_identity = v12_inputs_before.get(str(terminal_path.resolve()))
    if (
        terminal_identity is None
        or terminal_identity.get("sha256") != terminal_sha256_before
        or _sha256_file(terminal_path) != terminal_sha256_before
    ):
        raise RuntimeError("V12 P4 terminal changed between source selection and P5 snapshot")
    selection_item = next(
        item for item in contract["inputs"] if item["role"] == "R9_selection_transition"
    )
    expected_selection = (ROOT / selection_item["path"]).resolve()
    if (
        accepted_parent_selection_record.resolve() != expected_selection
        or _sha256_file(expected_selection) != selection_item["sha256"]
    ):
        raise ValueError("V11 P5 requires the contract-bound frozen R9 selection record")
    output_root = (
        Path(str(contract["artifact_prefix"])) / str(phase["comparison_output_root"])
    ).resolve()
    if output_root.exists():
        raise FileExistsError(f"refusing to overwrite V11 P5 output root: {output_root}")
    runtime_environment = _check_v11_runtime_envelope(MPI.COMM_WORLD)
    worker_identity = runtime_environment["v11_watchdog_worker_identity"]
    inputs_before = _v11_input_snapshot(contract, _V11_P5_INPUT_ROLES)
    source_before = _v11_source_snapshot()
    output_root.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    ledger = WorkflowLedger(output_root, Path(worker_identity["phase_path"]))
    completed_samples: dict[str, dict[str, Any]] = {}
    candidate_terminal_sha256 = terminal_sha256_before
    saved_primary_recovery = None
    try:
        ledger.set_phase("preflight")
        ledger.marker(
            "task43_v11_p5_worker_identity_bound",
            {
                "worker_identity": worker_identity,
                "runtime_environment": runtime_environment,
                "input_sha256": inputs_before,
                "v12_p2_p4_input_sha256": v12_inputs_before,
                "source_sha256": source_before,
                "contract_sha256": contract_sha256,
            },
        )
        accepted = _load_accepted_parent(expected_selection)
        if accepted.get("candidate_id") != "round9_p_up":
            raise ValueError("V11 P5 selected parent is not the frozen R9 p-up endpoint")
        reference = _restore_candidate(
            Path(accepted["run_root"]), output_root / "restore_R9"
        )
        _require_v11_watchdog_worker_identity(
            expected_identity=worker_identity, require_unused_phase_file=False
        )
        if saved_primary_mode:
            candidate = _v15_restore_h_saved_primary_candidate(
                candidate_run_root,
                output_root,
                contract_sha256=contract_sha256,
                recovery_binding=recovery_binding,
                saved_binding=saved_primary_binding,
                terminal=terminal,
            )
            saved_primary_recovery = candidate["saved_primary_recovery"]
        else:
            candidate = _restore_candidate(
                candidate_run_root,
                output_root / "restore_R9_H8",
                v11_contract=contract,
                v11_contract_sha256=contract_sha256,
                v12_recovery_binding=recovery_binding,
            )
        _require_v11_watchdog_worker_identity(
            expected_identity=worker_identity, require_unused_phase_file=False
        )
        y6 = _restore_case_fields("Y6_1", output_root)
        _require_v11_watchdog_worker_identity(
            expected_identity=worker_identity, require_unused_phase_file=False
        )
        cases = {"R9": {**reference, "label": "R9"}, "R9_H8": candidate, "Y6_1": y6}
        quadrature_validation = base._validate_recorded_quadrature_and_cutoff(
            cases, labels=("R9", "Y6_1")
        )

        p4_controls = candidate["record"].get("numerical_controls", {})
        r9_controls = reference["record"].get("numerical_controls", {})
        expected_quadrature = contract["phases"]["P4"]["quadrature"]
        frozen_calibration = _json(
            ROOT / next(
                item["path"]
                for item in contract["inputs"]
                if item["role"] == "reference_calibration"
            )
        )
        expected_cutoff = frozen_calibration[
            "recorded_quadrature_and_cutoff_identity"
        ]["expected"]
        for label, controls in (("R9", r9_controls), ("R9_H8", p4_controls)):
            actual_identity = {
                "volume_degree": int(controls["volume_quadrature_degree"]),
                "surface_and_incident_degree": int(
                    controls["incident_and_port_quadrature_degree"]
                ),
                "volume_rule": str(controls["volume_quadrature_rule"]),
                "cutoff_policy": str(controls["sparse_cutoff_policy"]),
                "cutoff_relative_tolerance": float(
                    controls["sparse_cutoff_relative_tolerance"]
                ),
            }
            expected_identity = {
                "volume_degree": int(expected_quadrature["volume"]),
                "surface_and_incident_degree": int(
                    expected_quadrature["incident_and_port"]
                ),
                **expected_cutoff,
            }
            if actual_identity != expected_identity:
                raise ValueError(f"V11 P5 {label} q/cutoff differs from the frozen R9 profile")
            if controls.get("ordered_mode_count") != 612:
                raise ValueError(f"V11 P5 {label} does not contain exactly 612 R13 modes")
            if controls.get("port_amplitude_scale_policy") != "boundary_magnitude_scaled_r5_v1":
                raise ValueError(f"V11 P5 {label} does not use the qualified Task43 amplitude gauge")
        physics = base._validate_common_physics(
            cases, labels=("R9", "R9_H8", "Y6_1")
        )
        modal_physics = base._validate_mode_physics(
            cases, labels=("R9", "R9_H8", "Y6_1")
        )
        full_mode_physics = {
            label: _post_selection_full_mode_physics(case)
            for label, case in cases.items()
        }
        expected_keys = {
            (side, m, n, pol)
            for side in ("top", "bottom")
            for m in range(-4, 5)
            for n in range(-8, 9)
            for pol in ("s", "p")
        }
        for label, case in cases.items():
            keys, amplitudes, rows = base._modal_identity(case["mode_payload"], label)
            if len(keys) != 612 or set(keys) != expected_keys or not np.isfinite(amplitudes).all():
                raise ValueError(f"V11 P5 {label} lacks the exact finite R13 mode set")
            if any(
                not all(np.isfinite(np.asarray(row[field], dtype=np.float64)).all()
                        for field in ("alpha", "gamma", "beta", "kz", "refractive_index"))
                or not np.isfinite(float(row["power_ratio"]))
                for row in rows
            ):
                raise ValueError(f"V11 P5 {label} has a nonfinite modal observable")
        p2_plan_path = Path(recovery_binding["plan_output_path"]).resolve()
        p2_audit_path = p2_plan_path.parent / "v11_r9_h8.audit.json"
        p2_audit = _json(p2_audit_path)
        p4_space = candidate["record"]["p4_preassembly_space_audit"]
        r9_dofs = int(
            reference["record"]["recovered_solution_storage"]["independent_active_fe_dofs"]
        )
        h_dofs = int(
            candidate["record"]["recovered_solution_storage"]["independent_active_fe_dofs"]
        )
        p2_space_match = {
            "p2_plan_sha256": p4_space.get("p2_plan_sha256") == _sha256_file(p2_plan_path),
            "p2_audit_sha256": p4_space.get("p2_audit_sha256") == _sha256_file(p2_audit_path),
            "actual_fe": p4_space.get("actual", {}).get("independent_active_fe_dofs")
            == p2_audit.get("dofs", {}).get("independent_active_fe_dofs"),
            "positive_fe_increment": int(candidate["record"]["recovered_solution_storage"]["independent_active_fe_dofs"])
            > int(contract["phases"]["P4"]["required_fe_bounds"]["parent_fe_dofs"]),
            "accepted_r9_fe_matches_contract": r9_dofs
            == int(contract["phases"]["P4"]["required_fe_bounds"]["parent_fe_dofs"]),
            "strict_fe_upper": int(candidate["record"]["recovered_solution_storage"]["independent_active_fe_dofs"])
            < int(contract["phases"]["P4"]["required_fe_bounds"]["target_exclusive_upper"]),
        }
        if not all(p2_space_match.values()):
            raise ValueError("V11 P5 P4 actual mesh/authority/FE does not match the frozen P2 audit")
        _require_v11_watchdog_worker_identity(
            expected_identity=worker_identity, require_unused_phase_file=False
        )
        ledger.set_phase("postprocess")
        ledger.marker(
            "task43_v11_p5_restores_and_modal_physics_pass",
            {
                "candidate_id": "v11_r9_h8",
                "accepted_parent_candidate_id": accepted["candidate_id"],
                "p2_space_match": p2_space_match,
                "full_mode_physics": full_mode_physics,
            },
        )
        results: dict[str, Any] = {}
        reference_case = cases["Y6_1"]
        pair_cases = {"R9": cases["R9"], "R9_H8": cases["R9_H8"]}
        for order in (8, 10):
            quadrature = build_common_volume_quadrature(
                [case["axes"] for case in cases.values()], gauss_order=order
            )
            points = np.asarray(quadrature.points_nm, dtype=np.float64)
            weights = np.asarray(quadrature.weights_nm3, dtype=np.float64)
            volume = float(np.sum(weights, dtype=np.float64))
            if (
                not np.isfinite(points).all()
                or not np.isfinite(weights).all()
                or np.any(weights <= 0.0)
                or abs(volume - 350000.0) > 1.0e-8
            ):
                raise ValueError(f"V11 P5 q{order} common domain/weights are invalid")
            material_breakpoints = (
                (0.0, 16.5, 33.5, 50.0),
                (0.0, 15.0, 35.0, 50.0),
                (-10.0, 0.0, 120.0, 130.0),
            )
            for axis, required in zip(
                quadrature.axis_breakpoints_nm, material_breakpoints, strict=True
            ):
                if any(
                    not np.any(np.isclose(axis, value, rtol=0.0, atol=1.0e-12))
                    for value in required
                ):
                    raise ValueError(f"V11 P5 q{order} common rule omits a material/domain boundary")
            samples: dict[str, dict[str, np.ndarray]] = {}
            owners: dict[str, dict[str, np.ndarray]] = {}
            for label, case in cases.items():
                samples[label] = _sample_field(case, points)
                if not all(np.isfinite(value).all() for value in samples[label].values()):
                    raise ValueError(f"V11 P5 q{order} {label} samples are nonfinite")
                global_cell_ids, local_slots = base._cell_slot_for_points(
                    case["mesh_data"].mesh, case["axes"], points
                )
                if local_slots.shape != (points.shape[0],):
                    raise ValueError(f"V11 P5 q{order} {label} owner map has a bad layout")
                owners[label] = {
                    "cell_global_ids": global_cell_ids,
                    "point_cell_local_slots": local_slots,
                    "point_cell_global_ids": global_cell_ids[local_slots],
                }
                _require_v11_watchdog_worker_identity(
                    expected_identity=worker_identity,
                    require_unused_phase_file=False,
                )
            sample_arrays: dict[str, np.ndarray] = {
                "points_nm": points,
                "weights_nm3": weights,
            }
            sample_arrays.update(
                {
                    f"{label}_{name}": value
                    for label, fields in samples.items()
                    for name, value in fields.items()
                }
            )
            sample_arrays.update(
                {
                    f"{label}_{name}": value
                    for label, values in owners.items()
                    for name, value in values.items()
                }
            )
            sample_path = output_root / f"v11_r9_h8_union_q{order}.npz"
            sample_record = write_atomic_npz(
                sample_path,
                sample_arrays,
                schema="task43.v11.union_comparison_samples.v1",
                classification="measured_shared_union_samples_nonofficial",
                identity={
                    "attempt_id": attempt_id,
                    "quadrature_order": order,
                    "candidate_id": "v11_r9_h8",
                    "reference_candidate_id": "round9_p_up",
                    "reference_label": "Y6_1",
                    "contract_sha256": contract_sha256,
                    "p4_terminal_sha256": candidate_terminal_sha256,
                    "p4_original_terminal_status": (
                        "FAILED" if saved_primary_mode else "SOLVED_PENDING_POSTPROCESS"
                    ),
                    "rule_sha256": quadrature.rule_sha256,
                    "sample_count": int(quadrature.point_count),
                "partition_box_count": int(quadrature.partition_box_count),
                "axis_breakpoints_nm": [
                    np.asarray(axis, dtype=np.float64).tolist()
                    for axis in quadrature.axis_breakpoints_nm
                ],
                    "integrated_domain_volume_nm3": volume,
                    "point_owner_scope": "actual per-case cell global ids/local slots for every shared point",
                },
            )
            completed_samples[f"q{order}"] = {
                "path": str(sample_path),
                "sha256": sample_record["npz_sha256"],
                "sample_count": int(quadrature.point_count),
                "point_hash": _sha256_bytes(points),
                "weight_hash": _sha256_bytes(weights),
                "rule_sha256": quadrature.rule_sha256,
            }
            _require_v11_watchdog_worker_identity(
                expected_identity=worker_identity,
                require_unused_phase_file=False,
            )
            results[f"q{order}"] = {}
            for label, candidate_case in pair_cases.items():
                modal = base._modal_comparison(reference_case, candidate_case)
                field = base._field_metrics(
                    samples["Y6_1"], samples[label], points, weights, reference_case["cfg"]
                )
                score = _j_infinity(modal, field)
                results[f"q{order}"][label] = {
                    "reference_label": "Y6_1",
                    "candidate_label": label,
                    "modal_metrics": modal,
                    "field_metrics": field,
                    "J_infinity": score,
                    "eta": float(field["G"]["relative_with_incident_floor"]),
                    "signed_observables": _v11_signed_mode_differences(
                        reference_case, candidate_case
                    ),
                }
            del samples, owners, sample_arrays
        thresholds = contract["fixed_h_diagnostic_thresholds"]
        q10_r9 = results["q10"]["R9"]
        q10_h = results["q10"]["R9_H8"]
        classification_q10 = _v11_fixed_h_classification(
            j_r9=float(q10_r9["J_infinity"]["value"]),
            j_h=float(q10_h["J_infinity"]["value"]),
            eta_r9=float(q10_r9["eta"]),
            eta_h=float(q10_h["eta"]),
            epsilon_j=float(thresholds["epsilon_J"]),
            epsilon_g=float(thresholds["epsilon_G"]),
        )
        q8_classification = _v11_fixed_h_classification(
            j_r9=float(results["q8"]["R9"]["J_infinity"]["value"]),
            j_h=float(results["q8"]["R9_H8"]["J_infinity"]["value"]),
            eta_r9=float(results["q8"]["R9"]["eta"]),
            eta_h=float(results["q8"]["R9_H8"]["eta"]),
            epsilon_j=float(thresholds["epsilon_J"]),
            epsilon_g=float(thresholds["epsilon_G"]),
        )
        sampling_classification = (
            "SAMPLING_SENSITIVITY_UNRESOLVED"
            if q8_classification["classification"] != classification_q10["classification"]
            else "q8_q10_diagnostic_classification_agrees"
        )
        if h_dofs <= r9_dofs:
            raise ValueError("V11 P5 h candidate has no positive actual Delta_FE")
        for classification in (classification_q10, q8_classification):
            classification["Delta_FE"] = h_dofs - r9_dofs
            classification["Delta_J_per_added_FE_dof"] = (
                classification["Delta_J"] / (h_dofs - r9_dofs)
            )
            classification["Delta_G_per_added_FE_dof"] = (
                classification["Delta_G"] / (h_dofs - r9_dofs)
            )
        source_after = _v11_source_snapshot()
        inputs_after = _v11_input_snapshot(contract, _V11_P5_INPUT_ROLES)
        if saved_primary_mode:
            v12_inputs_after = _v12_p5_input_snapshot(
                candidate_run_root,
                contract_sha256=contract_sha256,
                recovery_binding=recovery_binding,
                saved_primary_binding_path=saved_primary_recovery_binding_path,
            )
        else:
            v12_inputs_after = _v12_p5_input_snapshot(
                candidate_run_root,
                contract_sha256=contract_sha256,
                recovery_binding=recovery_binding,
            )
        _require_v11_watchdog_worker_identity(
            expected_identity=worker_identity, require_unused_phase_file=False
        )
        if (
            source_after != source_before
            or inputs_after != inputs_before
            or v12_inputs_after != v12_inputs_before
        ):
            raise RuntimeError("V11 P5 source/input identity changed during union comparison")
        record = {
            "schema": "task43.v11.union_comparison.v1",
            "status": "COMPLETE_DIAGNOSTIC_NOT_ACCEPTANCE",
            "classification": (
                "SAMPLING_SENSITIVITY_UNRESOLVED"
                if sampling_classification == "SAMPLING_SENSITIVITY_UNRESOLVED"
                else classification_q10["classification"]
            ),
            "qualification_boundary": "fixed-reference output response only; no continuous-error or accepted-state claim",
            "official_result": False,
            "passed": False,
            "selection_transition_written": False,
            "continuation_all_false": True,
            "attempt_id": attempt_id,
            "contract_path": str(contract_path.resolve()),
            "contract_sha256": contract_sha256,
            "v12_recovery_binding": recovery_binding,
            "reference_candidate_id": accepted["candidate_id"],
            "candidate_id": "v11_r9_h8",
            "reference_label": "Y6_1",
            "candidate_run_root": str(candidate_run_root.resolve()),
            "candidate_endpoint_sha256": (
                None
                if saved_primary_mode
                else _sha256_file(candidate_run_root / "task43_round1_candidate_record.json")
            ),
            "candidate_terminal_sha256": candidate_terminal_sha256,
            "candidate_terminal_status": (
                "FAILED" if saved_primary_mode else "SOLVED_PENDING_POSTPROCESS"
            ),
            "saved_primary_recovery": saved_primary_recovery,
            "candidate_primary_packet_sha256": _sha256_file(candidate_run_root / "primary_state.npz"),
            "P4_launch_manifest_sha256": _sha256_file(candidate_run_root.parent / "snapshots/launch_manifest.json"),
            "P4_watchdog_summary_sha256": _sha256_file(candidate_run_root.parent / "watchdog/summary.json"),
            "P4_launcher_exit_code_sha256": _sha256_file(candidate_run_root.parent / "launcher_exit_code.txt"),
            "P4_watchdog_exit_code_sha256": _sha256_file(candidate_run_root.parent / "watchdog_exit_code.txt"),
            "accepted_parent_selection_path": str(expected_selection),
            "accepted_parent_selection_sha256": selection_item["sha256"],
            "P2_plan_path": str(p2_plan_path),
            "P2_plan_sha256": _sha256_file(p2_plan_path),
            "P2_actual_audit_sha256": _sha256_file(p2_audit_path),
            "P2_joined_terminal_path": str(
                Path(recovery_binding["support_root"]) / "v12_p2_joined_terminal.json"
            ),
            "P2_joined_terminal_sha256": _sha256_file(
                Path(recovery_binding["support_root"])
                / "v12_p2_joined_terminal.json"
            ),
            "P2_source_id": recovery_binding["p2_source_id"],
            "P4_restored_coefficient_binding": candidate.get(
                "v12_restoration_binding"
            ),
            "P4_preassembly_space_match": p2_space_match,
            "actual_FE": {"R9": r9_dofs, "R9_H8": h_dofs, "Delta_FE": h_dofs - r9_dofs},
            "same_physics": physics,
            "same_modal_physics": modal_physics,
            "full_612_physical_reconstruction": full_mode_physics,
            "recorded_quadrature_and_cutoff_identity": quadrature_validation,
            "case_identities": {
                label: {
                    "discretization_identity": {
                        "nedelec_degree": int(
                            case["record"].get("numerical_controls", {}).get(
                                "nedelec_degree",
                                case["record"].get("resolved_identity", {}).get(
                                    "nedelec_degree", 6
                                ),
                            )
                        ),
                        "floquet_constraint_mode": case["record"].get(
                            "resolved_config", {}
                        ).get(
                            "floquet_constraint_mode",
                            case["record"].get("resolved_identity", {}).get(
                                "floquet_constraint_mode"
                            ),
                        ),
                        "independent_active_fe_dofs": case["record"].get(
                            "recovered_solution_storage", {}
                        ).get(
                            "independent_active_fe_dofs",
                            case["record"].get("numerical_controls", {})
                            .get("active_space", {})
                            .get("independent_active_fe_dofs"),
                        ),
                        "ordered_mode_count": case["record"].get(
                            "numerical_controls", {}
                        ).get(
                            "ordered_mode_count",
                            case["record"].get("resolved_identity", {}).get(
                                "ordered_mode_count"
                            ),
                        ),
                    },
                    "mesh_identity": {
                        "recorded_mesh": case["record"].get(
                            "numerical_controls", {}
                        ).get(
                            "mesh",
                            {
                                key: case["record"].get("resolved_identity", {}).get(key)
                                for key in (
                                    "mesh_axes_nm",
                                    "global_cells",
                                    "mesh_cell_catalog_sha256",
                                )
                            },
                        ),
                        "restored_mesh_arrays": case.get("mesh_identity", {}),
                        "axes_nm_sha256": [
                            _sha256_bytes(np.asarray(axis, dtype=np.float64))
                            for axis in case["axes"]
                        ],
                    },
                    "solver_route_identity": (
                        {
                            key: case["record"].get("solver", {}).get(key)
                            for key in (
                                "requested_direct_factor_backend",
                                "actual_direct_factor_backend",
                                "actual_live_direct_factor_backend",
                                "official_result_scope",
                            )
                        }
                        | {
                            "assembly_backend": case["record"]
                            .get("numerical_controls", {})
                            .get("assembly_backend"),
                            "method": case["record"].get("method"),
                        }
                        if label != "Y6_1"
                        else {
                            "historical_execution_identity": case["record"].get(
                                "execution_identity"
                            ),
                            "source_module_sha256": case["record"].get(
                                "source_module_sha256"
                            ),
                            "route_scope": "restored historical Y6_1 direct-route record; no new solve",
                        }
                    ),
                }
                for label, case in cases.items()
            },
            "quadrature_orders": [8, 10],
            "sample_each_case_once_per_order": True,
            "common_domain_volume_nm3": 350000.0,
            "saved_union_samples": completed_samples,
            "results": results,
            "fixed_thresholds": thresholds,
            "q10_primary_classification": classification_q10,
            "q8_robustness_classification": q8_classification,
            "sampling_sensitivity": sampling_classification,
            "source_identity_start": source_before,
            "source_identity_end": source_after,
            "input_identity_start": inputs_before,
            "input_identity_end": inputs_after,
            "v12_p2_p4_input_identity_start": v12_inputs_before,
            "v12_p2_p4_input_identity_end": v12_inputs_after,
            "saved_primary_recovery_binding_sha256": (
                _V15_H_SAVED_PRIMARY_BINDING_SHA256 if saved_primary_mode else None
            ),
            "unchanged_source_and_inputs": True,
            "worker_identity": worker_identity,
            "runtime_environment": runtime_environment,
            "frozen_comparison_contract_sha256": next(
                item["sha256"]
                for item in contract["inputs"]
                if item["role"] == "frozen_comparison_contract"
            ),
            "wall_seconds": time.perf_counter() - started,
        }
        record_path = output_root / "v11_r9_h8_union_comparison.json"
        record_path.write_text(
            json.dumps(record, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        ledger.set_phase("complete")
        ledger.marker(
            "task43_v11_p5_union_comparison_complete",
            {"record_path": str(record_path), "record_sha256": _sha256_file(record_path)},
        )
        return record
    except BaseException as exc:
        failure = {
            "schema": "task43.v11.union_comparison_failure.v1",
            "status": "ACTION_ENDPOINT_NOT_QUALIFIED",
            "classification": "ACTION_ENDPOINT_NOT_QUALIFIED",
            "error": f"{type(exc).__name__}: {exc}",
            "attempt_id": attempt_id,
            "contract_sha256": contract_sha256,
            "official_result": False,
            "passed": False,
            "selection_transition_written": False,
            "completed_samples": completed_samples,
            "saved_primary_recovery": saved_primary_recovery,
            "source_identity_start": source_before,
            "input_identity_start": inputs_before,
        }
        failure_path = output_root / "v11_r9_h8_union_failure.json"
        if not failure_path.exists():
            failure_path.write_text(
                json.dumps(failure, indent=2, sort_keys=True, allow_nan=False) + "\n",
                encoding="utf-8",
            )
        try:
            ledger.set_phase("failed")
            ledger.marker("task43_v11_p5_union_comparison_failed", failure)
        except BaseException:
            pass
        raise


def compare_post_selection(
    stop_record: Path, assets_manifest: Path, reference_root: Path, output_root: Path,
) -> dict[str, Any]:
    """Compare frozen final records; this branch never marks or selects a parent."""
    if MPI.COMM_WORLD.size != 1:
        raise RuntimeError("post-selection comparison requires MPI1")
    binding = _post_selection_binding(stop_record)
    decision = binding["decision"]
    accepted = binding["accepted"]

    def checked_reference(value: dict[str, Any]) -> Path:
        path = Path(value["path"])
        path = path if path.is_absolute() else ROOT / path
        if _sha256_file(path) != value["sha256"]:
            raise ValueError(f"post-selection artifact hash differs: {path}")
        return path

    rejected_record = checked_reference(decision["evidence"]["PDE_record"])
    for name in ("PDE_storage", "PDE_modal_rows", "PDE_checkpoint"):
        checked_reference(decision["evidence"][name])
    rejected_root = rejected_record.parent
    contract = _json(COMPARISON_CONTRACT)
    acceptance = _json(ACCEPTANCE)
    calibration_path = checked_reference(acceptance["evidence"]["reference_and_quadrature"])
    checked_reference(acceptance["evidence"]["comparison_contract"])
    calibration = _json(calibration_path)
    candidate_roots = (accepted["run_root"], rejected_root)
    hard_gates = {}
    for run in candidate_roots:
        record = _json(run / "task43_round1_candidate_record.json")
        modal = _json(run / "solve/dtn_port_diffraction_orders_3d.json")
        gate = _recompute_candidate_hard_gates(record, modal, contract)
        if not gate["pass"]:
            raise ValueError("post-selection candidate fails raw numerical gates")
        hard_gates[record["candidate_identity"]["candidate_id"]] = gate
    if accepted["candidate_id"] == decision["scientific_candidate_id"]:
        raise ValueError("accepted and unaccepted diagnostic candidate ids must differ")
    if _json(rejected_record)["candidate_identity"]["candidate_id"] != decision["scientific_candidate_id"]:
        raise ValueError("rejected diagnostic candidate identity differs")
    if output_root.exists():
        raise FileExistsError(f"refusing to overwrite diagnostic output: {output_root}")
    output_root.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    sources = base._source_snapshot()
    sources["candidate_comparator_sha256"] = _sha256_file(Path(__file__))
    sources["candidate_records_sha256"] = _sha256_file(CANDIDATE_RECORDS)
    cases = {}
    for run in candidate_roots:
        case = _restore_candidate(run, output_root / run.name / run.parent.name)
        cases[case["label"]] = case
    candidates = tuple(cases)
    cases["Y6_1"] = _restore_case_fields("Y6_1", output_root)
    for label in ("Y5_1", "Y3", "Y3_2"):
        cases[label] = _restore_case_fields(
            label, output_root, reference_root=reference_root,
            post_selection_record=stop_record, assets_manifest=assets_manifest,
        )
    labels = tuple(cases)
    expected_keys = {(side, m, n, pol) for side in ("top", "bottom")
                     for m in range(-4, 5) for n in range(-8, 9) for pol in ("s", "p")}
    for label, case in cases.items():
        keys, amplitudes, rows = base._modal_identity(case["mode_payload"], label)
        if len(keys) != 612 or set(keys) != expected_keys or not np.all(np.isfinite(amplitudes)):
            raise ValueError(f"{label} lacks the complete finite unique612 inventory")
        if not all(np.isfinite(float(row["power_ratio"])) for row in rows):
            raise ValueError(f"{label} has nonfinite raw channel powers")
    full_mode_physics = {label: _post_selection_full_mode_physics(case) for label, case in cases.items()}
    physics = base._validate_common_physics(cases, labels=labels)
    modal_physics = base._validate_mode_physics(cases, labels=labels)
    quadrature_controls = base._validate_recorded_quadrature_and_cutoff(
        cases, labels=(candidates[0], "Y6_1", "Y5_1", "Y3", "Y3_2"),
    )
    candidate_physics = {
        label: _validate_candidate_physics(cases[label], cases["Y6_1"], calibration)
        for label in candidates
    }
    # The first entry of each pair is the reference and defines the denominator.
    pairs = [(reference, candidate) for reference in ("Y5_1", "Y3", "Y3_2")
             for candidate in candidates]
    pairs += [("Y6_1", external) for external in ("Y5_1", "Y3", "Y3_2")]
    modal_metrics = {
        f"{reference}__vs__{candidate}": base._modal_comparison(cases[reference], cases[candidate])
        for reference, candidate in pairs
    }
    rules = {}
    results = {}
    for order in (8, 10):
        quadrature = build_common_volume_quadrature([case["axes"] for case in cases.values()], gauss_order=order)
        volume = float(np.sum(quadrature.weights_nm3, dtype=np.float64))
        if not np.isfinite(volume) or abs(volume - 350000.0) > 1.0e-8:
            raise ValueError("post-selection actual quadrature volume differs")
        sampled = {}
        for label, case in cases.items():
            sampled[label] = _sample_field(case, quadrature.points_nm)
            if not all(np.all(np.isfinite(value)) for value in sampled[label].values()):
                raise ValueError(f"{label} has nonfinite volume field samples")
        path = output_root / f"post_selection_shared_q{order}.npz"
        arrays = {"points_nm": quadrature.points_nm, "weights_nm3": quadrature.weights_nm3}
        arrays.update({f"{label}_{name}": values for label, fields in sampled.items()
                       for name, values in fields.items()})
        np.savez(path, **arrays)
        rules[f"q{order}"] = {
            "rule_sha256": quadrature.rule_sha256, "sample_count": quadrature.point_count,
            "partition_boxes": quadrature.partition_box_count,
            "axis_breakpoints_nm": [axis.tolist() for axis in quadrature.axis_breakpoints_nm],
            "integrated_domain_volume_nm3": volume,
            "sample_bundle": str(path), "sample_bundle_sha256": _sha256_file(path),
            "scope": "New post-selection union, does not overwrite earlier frozen selection rule",
        }
        results[f"q{order}"] = {}
        for reference, candidate in pairs:
            name = f"{reference}__vs__{candidate}"
            field = base._field_metrics(sampled[reference], sampled[candidate],
                                       quadrature.points_nm, quadrature.weights_nm3, cases[reference]["cfg"])
            j = _j_infinity(modal_metrics[name], field)
            results[f"q{order}"][name] = {
                "reference_label": reference, "candidate_label": candidate,
                "field_metrics": field, "J_infinity": j,
                "same_frozen_thresholds_pass": bool(j["value"] <= 1.0),
                "failed_components": {key: value for key, value in j["components"].items() if value > 1.0},
            }
        del sampled, arrays
    observations = {}
    for name in modal_metrics:
        q8 = results["q8"][name]
        q10 = results["q10"][name]
        observations[name] = {
            "normalized_component_q10_minus_q8": {
                key: value - q8["J_infinity"]["components"][key]
                for key, value in q10["J_infinity"]["components"].items()},
            "absolute_field_difference_norm_q10_minus_q8": {
                key: value["difference_l2"] - q8["field_metrics"][key]["difference_l2"]
                for key, value in q10["field_metrics"].items() if "difference_l2" in value},
            "G_absolute_difference_norm_q10_minus_q8": q10["field_metrics"]["G"]["difference_g_norm"] - q8["field_metrics"]["G"]["difference_g_norm"],
            "any_frozen_component_pass_fail_changed": any(
                (value <= 1.0) != (q8["J_infinity"]["components"][key] <= 1.0)
                for key, value in q10["J_infinity"]["components"].items()),
            "scope": "Stricter postprocessing observation; no new hard threshold and no PDE q qualification",
        }
    sources_end = base._source_snapshot()
    sources_end["candidate_comparator_sha256"] = _sha256_file(Path(__file__))
    sources_end["candidate_records_sha256"] = _sha256_file(CANDIDATE_RECORDS)
    if sources != sources_end:
        raise ValueError("sources changed during post-selection comparison")
    record = {
        "schema": "task43.post-selection-comparison.v1",
        "status": "COMPLETE_DIAGNOSTIC_NOT_ACCEPTANCE", "selection_eligible": False,
        "run_role": "post_selection_validation_only",
        "frozen_selection_sha256": binding["selection_sha256"],
        "selection_stop_record_sha256": binding["stop_sha256"],
        "assets_manifest_sha256": _sha256_file(assets_manifest),
        "accepted_candidate": candidates[0], "unaccepted_diagnostic_candidate": candidates[1],
        "source_identity_start": sources, "source_identity_end": sources_end,
        "hard_gate_recalculation": hard_gates, "common_physics": physics,
        "modal_physics": modal_physics, "full_mode_physics_recalculation": full_mode_physics,
        "recorded_quadrature_controls": quadrature_controls,
        "candidate_physics": candidate_physics, "quadrature": rules,
        "modal_and_power_metrics": modal_metrics, "results": results,
        "q8_q10_observations": observations,
        "actual_external_FE": {label: cases[label]["record"]["resolved_identity"]["actual_FE_from_restored_constraints"]
                               for label in ("Y5_1", "Y3", "Y3_2")},
        "raw_modal_artifacts": {
            label: {"path": str((reference_root if label in ("Y5_1", "Y3", "Y3_2") else REFERENCE_ROOT)
                                 / label / "numerical_output/dtn_port_diffraction_orders_3d.json")}
            for label in ("Y6_1", "Y5_1", "Y3", "Y3_2")},
        "wall_seconds_through_record_construction": time.perf_counter() - started,
        "qualification_boundary": "Post-selection comparisons of stored fields only; no new accepted state, fresh PDE, continuum/q/R reference qualification, sidewall or matched cold-cost claim",
    }
    for value in record["raw_modal_artifacts"].values():
        value["sha256"] = _sha256_file(Path(value["path"]))
    (output_root / "post_selection_comparison.json").write_text(
        json.dumps(record, indent=2, sort_keys=True, allow_nan=False) + "\n")
    return record


def _v16_p8_read_and_bind_prevalidation_checkpoint(
    primary_packet_path: Path,
    primary_packet: Mapping[str, Any],
    checkpoint_npz_path: Path,
    checkpoint_json_path: Path,
    *,
    expected_primary_sha256: str,
    expected_checkpoint_sha256: str,
    expected_record_sha256: str,
) -> dict[str, dict[str, Any]]:
    """Read both saved packets and bind every pre-validation array to primary."""

    primary_packet_path = Path(primary_packet_path)
    checkpoint_npz_path = Path(checkpoint_npz_path)
    checkpoint_json_path = Path(checkpoint_json_path)
    paths = (primary_packet_path, checkpoint_npz_path, checkpoint_json_path)
    if any(
        not path.is_absolute()
        or path.resolve() != path
        or path.is_symlink()
        or not path.is_file()
        for path in paths
    ):
        raise FileNotFoundError("V16 P8 primary/pre-validation packet is missing")
    initial_hashes = {
        "primary": _sha256_file(primary_packet_path),
        "checkpoint": _sha256_file(checkpoint_npz_path),
        "record": _sha256_file(checkpoint_json_path),
    }
    if initial_hashes != {
        "primary": expected_primary_sha256,
        "checkpoint": expected_checkpoint_sha256,
        "record": expected_record_sha256,
    }:
        raise ValueError("V16 P8 primary/pre-validation inputs changed before read")

    checkpoint_metadata = primary_packet.get("identity", {}).get(
        "pre_validation_checkpoint", {}
    )
    declared_checkpoint_arrays = checkpoint_metadata.get("arrays", {})
    if (
        checkpoint_metadata.get("npz_path") != str(checkpoint_npz_path)
        or checkpoint_metadata.get("npz_sha256") != expected_checkpoint_sha256
        or checkpoint_metadata.get("sidecar_path") != str(checkpoint_json_path)
        or checkpoint_metadata.get("sidecar_sha256") != expected_record_sha256
        or not isinstance(declared_checkpoint_arrays, Mapping)
        or not declared_checkpoint_arrays
    ):
        raise ValueError("V16 P8 primary does not bind the fixed pre-validation files")

    checkpoint_record = _json(checkpoint_json_path)
    if (
        checkpoint_record.get("schema") != "task43.pre-validation-field-checkpoint.v1"
        or checkpoint_record.get("npz_path") != str(checkpoint_npz_path)
        or checkpoint_record.get("npz_sha256") != expected_checkpoint_sha256
        or checkpoint_record.get("identity") != checkpoint_metadata.get("identity")
        or checkpoint_record.get("arrays") != declared_checkpoint_arrays
    ):
        raise ValueError("V16 P8 pre-validation sidecar differs from the primary binding")

    restored_identities: dict[str, dict[str, Any]] = {}
    with np.load(primary_packet_path, allow_pickle=False) as primary_archive:
        if "__task43_record_json__" not in primary_archive.files:
            raise ValueError("V16 P8 primary packet lacks its embedded identity")
        embedded = json.loads(
            np.asarray(primary_archive["__task43_record_json__"], dtype=np.uint8)
            .tobytes()
            .decode("utf-8")
        )
        if (
            embedded.get("schema") != "task43.v16.p8.primary_state.v1"
            or embedded.get("identity") != primary_packet.get("identity")
            or embedded.get("arrays") != primary_packet.get("arrays")
            or set(primary_archive.files)
            != set(primary_packet.get("arrays", {})) | {"__task43_record_json__"}
        ):
            raise ValueError("V16 P8 primary packet identity changed before checkpoint read")
        with np.load(checkpoint_npz_path, allow_pickle=False) as checkpoint_archive:
            if set(checkpoint_archive.files) != set(declared_checkpoint_arrays):
                raise ValueError("V16 P8 pre-validation checkpoint inventory differs")
            for name, declared in declared_checkpoint_arrays.items():
                packet_name = "recovered_" + str(name)
                if packet_name not in primary_archive.files:
                    raise ValueError(
                        f"V16 P8 primary packet lacks checkpoint array {packet_name}"
                    )
                checkpoint_values = np.asarray(checkpoint_archive[name])
                primary_values = np.asarray(primary_archive[packet_name])
                checkpoint_identity = _checkpoint_array_identity(checkpoint_values)
                packet_identity = _checkpoint_array_identity(primary_values)
                packet_declared = primary_packet.get("arrays", {}).get(packet_name, {})
                if any(
                    checkpoint_identity.get(key) != declared.get(key)
                    for key in ("dtype", "shape", "sha256")
                ):
                    raise ValueError(
                        f"V16 P8 pre-validation array identity differs: {name}"
                    )
                if any(
                    packet_identity.get(key) != packet_declared.get(key)
                    for key in ("dtype", "shape", "sha256")
                ):
                    raise ValueError(f"V16 P8 primary array identity differs: {packet_name}")
                if (
                    primary_values.dtype != checkpoint_values.dtype
                    or primary_values.shape != checkpoint_values.shape
                    or not np.array_equal(primary_values, checkpoint_values)
                ):
                    raise ValueError(
                        f"V16 P8 primary and pre-validation arrays differ: {name}"
                    )
                restored_identities[str(name)] = checkpoint_identity

    if {
        "primary": _sha256_file(primary_packet_path),
        "checkpoint": _sha256_file(checkpoint_npz_path),
        "record": _sha256_file(checkpoint_json_path),
    } != initial_hashes:
        raise RuntimeError("V16 P8 primary/pre-validation input changed while read")
    return restored_identities


def _v16_p8_frozen_endpoint(
    contract_path: Path,
    accepted_parent_selection_record: Path,
    *,
    execution_recovery_path: Path | None = None,
) -> dict[str, Any]:
    from benchmarks.task43_hp_adaptivity import h100_anchor
    from benchmarks.task43_hp_adaptivity.round1_candidates import (
        _load_v18_p8_execution_recovery,
        _load_v16_p8_contract,
        _validate_v18_p8_phase_identity,
        _v18_p8_phase_root,
        _v16_p8_input_snapshot,
    )

    contract, contract_sha256 = _load_v16_p8_contract(contract_path)
    execution_recovery = (
        _load_v18_p8_execution_recovery(
            execution_recovery_path,
            contract=contract,
            contract_sha256=contract_sha256,
            phase="C",
        )
        if execution_recovery_path is not None
        else None
    )
    if execution_recovery is not None:
        _validate_v18_p8_phase_identity(
            execution_recovery,
            phase="C",
            actual_root=_v18_p8_phase_root(execution_recovery, "C"),
            manifest_path=Path(execution_recovery["manifest_path"]),
            manifest_sha256=execution_recovery["manifest_sha256"],
            contract_sha256=contract_sha256,
        )
    run_root = (
        _v18_p8_phase_root(execution_recovery, "F") / "run"
        if execution_recovery is not None
        else (
            Path(str(contract["artifact_prefix"]))
            / str(contract["phases"]["F"]["root"])
            / "run"
        ).resolve()
    )
    launch_root = run_root.parent
    launch_manifest_path = launch_root / "snapshots/launch_manifest.json"
    launch_manifest = _json(launch_manifest_path)
    source_id = str(launch_manifest.get("space_source_id", ""))
    context_options = (
        {"execution_recovery_path": execution_recovery_path}
        if execution_recovery_path is not None
        else {}
    )
    _loaded_contract, loaded_sha, space_binding = _load_v16_p8_context(
        contract_path, source_id=source_id, run_root=run_root, **context_options
    )
    if loaded_sha != contract_sha256:
        raise RuntimeError("V16 P8 contract changed during C first-read binding")

    joined_path = (
        _v18_p8_phase_root(execution_recovery, "F")
        / "v18_p8_endpoint_joined_terminal.json"
        if execution_recovery is not None
        else (
            Path(str(contract["artifact_prefix"]))
            / str(contract["phases"]["F"]["joined_terminal_path"])
        ).resolve()
    )
    terminal_path = run_root / "task43_v16_p8_primary_terminal.json"
    endpoint_path = run_root / "task43_round1_candidate_record.json"
    packet_path = run_root / "primary_state.npz"
    raw_path = run_root / "primary_raw_vector_audit.json"
    p8_plan_path = run_root / "candidate_plan.json"
    prevalidation_npz_path = run_root / "pre_validation_checkpoint.npz"
    prevalidation_json_path = run_root / "pre_validation_checkpoint.json"
    lifecycle_paths = {
        "joined": joined_path,
        "terminal": terminal_path,
        "endpoint": endpoint_path,
        "primary_packet": packet_path,
        "raw_gate_checkpoint": raw_path,
        "candidate_plan": p8_plan_path,
        "prevalidation_checkpoint": prevalidation_npz_path,
        "prevalidation_record": prevalidation_json_path,
        "launch_manifest": launch_manifest_path,
        "watchdog_summary": launch_root / "watchdog/summary.json",
        "launcher_exit": launch_root / "launcher_exit_code.txt",
        "watchdog_exit": launch_root / "watchdog_exit_code.txt",
        "source_head": launch_root / "source_head.txt",
    }
    if any(not path.is_file() or path.is_symlink() for path in lifecycle_paths.values()):
        raise FileNotFoundError("V16 P8 C requires the complete root-joined F product set")
    product_before = {
        name: _sha256_file(path) for name, path in lifecycle_paths.items()
    }
    joined = _json(joined_path)
    terminal = _json(terminal_path)
    endpoint = _json(endpoint_path)
    raw_checkpoint = _json(raw_path)
    watchdog_summary = _json(lifecycle_paths["watchdog_summary"])
    source_head = str(launch_manifest.get("head", ""))
    observation = joined.get("root_observation_record")
    if not isinstance(observation, Mapping):
        raise ValueError("V16 P8 F joined terminal has no root observation record")
    observation_path = Path(str(observation.get("path", "")))
    observation_sha256 = str(observation.get("sha256", ""))
    if (
        not observation_path.is_absolute()
        or observation_path.resolve() != observation_path
        or observation_path.is_symlink()
        or not observation_path.is_file()
        or _sha256_file(observation_path) != observation_sha256
    ):
        raise ValueError("V16 P8 F root observation record is missing or changed")
    lifecycle_paths["root_observation_record"] = observation_path
    product_before["root_observation_record"] = observation_sha256
    if (
        joined.get("schema") != "task43.v16.p8-endpoint-root-joined-terminal.v1"
        or joined.get("status") != "F_COMPLETE_ROOT_VERIFIED"
        or joined.get("space_source_id") != source_id
        or joined.get("contract_sha256") != contract_sha256
        or joined.get("review_commit") != "f72e1c8d031de7acc374f0806ddac06099c461c4"
        or joined.get("source_head") != source_head
        or joined.get("launcher_exit_code") != 0
        or joined.get("watchdog_exit_code") != 0
        or joined.get("worker_exit_code") != 0
        or joined.get("descendants_cleared") is not True
        or joined.get("remaining_child_pids") != []
        or set(joined.get("products", {}))
        != {"terminal", "endpoint", "primary_packet", "raw_gate_checkpoint"}
        or set(joined.get("gates", {}))
        != {"source", "input", "resource", "trace", "raw", "space", "numerical_endpoint"}
        or (
            execution_recovery is not None
            and joined.get("execution_recovery_binding")
            != {
                "path": execution_recovery["manifest_path"],
                "sha256": execution_recovery["manifest_sha256"],
                "phase": "F",
            }
        )
        or (
            execution_recovery is not None
            and launch_manifest.get("execution_recovery_binding")
            != {
                "path": execution_recovery["manifest_path"],
                "sha256": execution_recovery["manifest_sha256"],
                "phase": "F",
            }
        )
    ):
        raise ValueError("V16 P8 F root-joined terminal is not a successful verified endpoint")
    if (
        terminal.get("schema") != "task43.v16.p8.primary-terminal.v1"
        or terminal.get("phase") != "R9_P8"
        or terminal.get("status") != "SOLVED_PRIMARY_PENDING_PAIRED_COMPARISON"
        or terminal.get("official_result") is not False
        or terminal.get("passed") is not False
        or terminal.get("continuation_all_false") is not True
        or terminal.get("contract_binding", {}).get("sha256") != contract_sha256
        or terminal.get("space_source_binding", {}).get("space_source_id") != source_id
        or endpoint.get("schema") != "task43.v16.p8.primary-endpoint.v1"
        or endpoint.get("phase") != "R9_P8"
        or endpoint.get("status") != "SOLVED_PRIMARY_PENDING_PAIRED_COMPARISON"
        or endpoint.get("official_result") is not False
        or endpoint.get("selection_eligible") is not False
        or endpoint.get("continuation_all_false") is not True
        or endpoint.get("gates", {}).get("pass") is not True
        or endpoint.get("preassembly_space_audit", {}).get("pass") is not True
        or endpoint.get("actual_absorption_form_audit", {}).get("status")
        != "actual_forms_observed"
        or terminal.get("endpoint_record", {}).get("path") != str(endpoint_path.resolve())
        or terminal.get("endpoint_record", {}).get("sha256") != product_before["endpoint"]
        or terminal.get("primary_packet", {}).get("npz_path") != str(packet_path.resolve())
        or terminal.get("primary_packet", {}).get("npz_sha256") != product_before["primary_packet"]
        or terminal.get("primary_raw_vector_audit_checkpoint", {}).get("path")
        != str(raw_path.resolve())
        or terminal.get("primary_raw_vector_audit_checkpoint", {}).get("sha256")
        != product_before["raw_gate_checkpoint"]
        or endpoint.get("primary_packet") != terminal.get("primary_packet")
        or endpoint.get("primary_raw_vector_audit_checkpoint")
        != terminal.get("primary_raw_vector_audit_checkpoint")
        or raw_checkpoint.get("pass") is not True
        or raw_checkpoint.get("official_result") is not False
        or raw_checkpoint.get("passed") is not False
    ):
        raise ValueError("V16 P8 F endpoint, primary packet, raw checkpoint or terminal differs")
    for name, path in (
        ("terminal", terminal_path),
        ("endpoint", endpoint_path),
        ("primary_packet", packet_path),
        ("raw_gate_checkpoint", raw_path),
    ):
        item = joined["products"][name]
        if (
            not isinstance(item, Mapping)
            or item.get("path") != str(path.resolve())
            or item.get("sha256") != product_before[name]
        ):
            raise ValueError(f"V16 P8 F joined {name} product identity differs")
    for name, gate in joined["gates"].items():
        evidence = gate.get("evidence") if isinstance(gate, Mapping) else None
        if not isinstance(gate, Mapping) or gate.get("pass") is not True or not isinstance(evidence, Mapping):
            raise ValueError(f"V16 P8 F root {name} gate did not pass with evidence")
        evidence_path = Path(str(evidence.get("path", "")))
        evidence_sha = str(evidence.get("sha256", ""))
        if (
            not evidence_path.is_absolute()
            or evidence_path.resolve() != evidence_path
            or not evidence_path.is_file()
            or _sha256_file(evidence_path) != evidence_sha
        ):
            raise ValueError(f"V16 P8 F {name} gate evidence is missing or changed")
        lifecycle_paths[f"gate_{name}"] = evidence_path
        product_before[f"gate_{name}"] = evidence_sha
    if (
        watchdog_summary.get("classification") != "COMPLETED"
        or watchdog_summary.get("leader_exit_code") != 0
        or watchdog_summary.get("descendants_cleared") is not True
        or watchdog_summary.get("remaining_child_pids") != []
        or lifecycle_paths["launcher_exit"].read_text(encoding="ascii").strip() != "0"
        or lifecycle_paths["watchdog_exit"].read_text(encoding="ascii").strip() != "0"
        or lifecycle_paths["source_head"].read_text(encoding="ascii").strip() != source_head
    ):
        raise ValueError("V16 P8 F watchdog/launcher lifecycle did not complete cleanly")

    from benchmarks.task43_hp_adaptivity import round1_candidates

    extra_inputs = (
        {
            execution_recovery["manifest_path"]: execution_recovery[
                "manifest_sha256"
            ],
            execution_recovery["tracked_summary_path"]: execution_recovery[
                "tracked_summary_sha256"
            ],
            execution_recovery["test_terminal_path"]: execution_recovery[
                "test_terminal_sha256"
            ],
            execution_recovery["test_qualification_path"]: execution_recovery[
                "test_qualification_sha256"
            ],
            execution_recovery["test_root_observation_path"]: execution_recovery[
                "test_root_observation_sha256"
            ],
            execution_recovery["runtime_identity_path"]: execution_recovery[
                "runtime_identity_sha256"
            ],
            execution_recovery["launch_script_path"]: execution_recovery[
                "launch_script_sha256"
            ],
        }
        if execution_recovery is not None
        else None
    )
    contract_inputs = (
        _v16_p8_input_snapshot(contract, additional_inputs=extra_inputs)
        if extra_inputs is not None
        else _v16_p8_input_snapshot(contract)
    )
    source_snapshot = _v11_source_snapshot()
    source_snapshot[Path(contract_path).resolve().relative_to(ROOT).as_posix()] = contract_sha256
    launch_sources = {
        str(item.get("path")): str(item.get("sha256"))
        for item in launch_manifest.get("source", [])
        if isinstance(item, Mapping)
    }
    if launch_sources != source_snapshot:
        raise ValueError("V16 P8 F source snapshot differs from the current frozen worker source set")
    selection = next(
        item for item in contract["inputs"] if item["role"] == "R9_selection_transition"
    )
    expected_selection = (ROOT / selection["path"]).resolve()
    if (
        accepted_parent_selection_record.resolve() != expected_selection
        or _sha256_file(expected_selection) != selection["sha256"]
    ):
        raise ValueError("V16 P8 C requires the fixed accepted R9 parent selection")

    endpoint_identity = endpoint.get("endpoint_identity", {})
    candidate_identity = terminal.get("candidate_identity", {})
    primary_packet = terminal.get("primary_packet", {})
    raw_identity = raw_checkpoint.get("identity", {})
    p8_plan_sha256 = _sha256_file(p8_plan_path)
    p8_plan = _json(p8_plan_path)
    orders_path = Path(str(endpoint.get("power", {}).get("channel_rows_file", ""))).resolve()
    if (
        not orders_path.is_absolute()
        or orders_path.resolve() != orders_path
        or orders_path.is_symlink()
        or not orders_path.is_file()
    ):
        raise ValueError("V16 P8 modal rows path is missing or noncanonical")
    lifecycle_paths["modal_orders"] = orders_path
    product_before["modal_orders"] = _sha256_file(orders_path)
    if (
        endpoint_identity.get("schema") != "task43.v16.p8.endpoint-identity.v1"
        or endpoint_identity.get("contract_sha256") != contract_sha256
        or terminal.get("candidate_plan_sha256") != p8_plan_sha256
        or endpoint.get("candidate_plan_sha256") != p8_plan_sha256
        or candidate_identity.get("candidate_id") != "v16_r9_p8"
        or candidate_identity.get("action") != "p_up"
        or p8_plan.get("task43_candidate", {}).get("candidate_id") != "v16_r9_p8"
        or p8_plan.get("task43_candidate", {}).get("action") != "p_up"
        or product_before["modal_orders"]
        != endpoint.get("power", {}).get("channel_rows_sha256")
    ):
        raise ValueError("V16 P8 candidate plan, endpoint identity or modal rows differ")
    modal_payload = _json(orders_path)
    modal_rows = modal_payload.get("orders")
    expected_modes = {
        (side, m, n, polarization)
        for side in ("top", "bottom")
        for m in range(-4, 5)
        for n in range(-8, 9)
        for polarization in ("s", "p")
    }
    if (
        not isinstance(modal_rows, list)
        or len(modal_rows) != 612
        or len({base._mode_key(row) for row in modal_rows}) != 612
        or {base._mode_key(row) for row in modal_rows} != expected_modes
        or any(
            not np.isfinite(float(row.get("power_ratio", np.nan)))
            or not np.isfinite(float(row.get("R", np.nan)))
            or not np.isfinite(float(row.get("T", np.nan)))
            for row in modal_rows
        )
    ):
        raise ValueError("V16 P8 endpoint does not contain the complete finite ordered 612 modes")
    power_record = endpoint.get("power", {})
    aggregate = modal_payload.get("metrics", {})
    avol = float(power_record.get("A_volume_total", np.nan))
    r_total = float(aggregate.get("R_total", np.nan))
    t_total = float(aggregate.get("T_total", np.nan))
    closure = r_total + t_total + avol - 1.0
    physics = contract["physics"]
    solver = endpoint.get("solver", {})
    if (
        not all(np.isfinite(value) for value in (avol, r_total, t_total, closure))
        or abs(closure) > float(contract["science_gates"]["energy_closure_abs_max"])
        or endpoint.get("independent_active_fe_dofs")
        != endpoint_identity.get("numerical_controls", {}).get(
            "independent_active_fe_dofs"
        )
        or endpoint.get("independent_active_fe_dofs")
        != endpoint.get("preassembly_space_audit", {}).get("actual_space", {}).get(
            "independent_fe_dofs"
        )
        or not (
            int(contract["parent"]["independent_fe_dofs"])
            < int(endpoint.get("independent_active_fe_dofs", -1))
            < int(contract["science_gates"]["fe_exclusive_bounds"][1])
        )
        or int(aggregate.get("dtn_port_mode_count", -1)) != 612
        or int(endpoint_identity.get("numerical_controls", {}).get("modal_selection", {}).get("count", -1)) != 612
        or int(endpoint_identity.get("numerical_controls", {}).get("quadrature_degree", {}).get("volume", -1)) != int(physics["operator_volume_q"])
        or int(endpoint_identity.get("numerical_controls", {}).get("quadrature_degree", {}).get("ports", -1)) != int(physics["incident_port_q"])
        or solver.get("actual_direct_factor_backend") != "mumps"
        or solver.get("actual_live_direct_factor_backend") != "mumps"
    ):
        raise ValueError("V16 P8 actual FE, modal, backend or energy endpoint gate differs")

    h8_raw = {item["role"]: item for item in contract["inputs"]}
    old_comparison = _json(ROOT / h8_raw["V15_P5_comparison_record"]["path"])
    p5_geometry = space_binding["space_audit"].get("saved_p5_geometry_gate", {})
    if p5_geometry.get("pass") is not True:
        raise ValueError("V16 P8 selected S source did not qualify the original P5 samples")
    raw_gate = endpoint.get("primary_raw_vector_audit", {})
    if (
        raw_gate.get("pass") is not True
        or raw_checkpoint.get("audit") != raw_gate
        or raw_identity.get("primary_packet") != primary_packet
    ):
        raise ValueError("V16 P8 endpoint raw gate and durable checkpoint differ")

    raw_keys = {
        "returned_trace_dtn_rhs",
        "returned_trace_dtn_solution",
        "returned_trace_dtn_b_minus_Ax",
        "full_active_reduced_trace_dtn_residual_Ax_minus_b_owned",
        "full_active_reduced_trace_dtn_residual_trace_metric_action",
        "full_active_reduced_trace_dtn_rhs_owned",
        "full_active_reduced_trace_dtn_solution_owned",
        "full_active_reduced_trace_dtn_rhs_trace_metric_action",
        "full_active_active_full_rhs",
        "full_active_active_full_solution",
        "full_active_eliminated_active_interior_residual",
        "recovered_active_full_rhs_owned",
        "recovered_active_full_solution_owned",
        "independent_A6_independent_active_residual_trace",
        "independent_A6_independent_active_residual_cell_interior",
        "independent_A6_independent_active_modal_lower_solver_gauge",
        "independent_A6_independent_active_rhs_trace",
        "independent_A6_independent_active_rhs_cell_interior",
        "independent_A6_independent_active_modal_lower_solver_gauge_rhs",
        "normal_before_normal_correction_rhs",
        "normal_before_normal_correction_solution",
        "normal_before_normal_correction_residual_b_minus_Ax",
        "normal_after_normal_correction_rhs",
        "normal_after_normal_correction_solution",
        "normal_after_normal_correction_residual_b_minus_Ax",
    }
    mesh_packet_keys = {
        "mesh_geometry_coordinates_nm": "recovered_mesh_geometry_coordinates_nm",
        "mesh_geometry_dofmap": "recovered_mesh_geometry_dofmap",
        "mesh_owned_cell_global_ids": "recovered_mesh_owned_cell_global_ids",
        "mesh_cell_vertex_dofmap": "recovered_mesh_cell_vertex_dofmap",
        "p6_function_space_cell_dofmap": "recovered_p6_function_space_dofmap",
        "p6_owned_global_dof_block_ids": "recovered_p6_owned_global_dof_block_ids",
        "p6_ghost_global_dof_block_ids": "recovered_p6_ghost_global_dof_block_ids",
    }
    loaded_arrays: dict[str, np.ndarray] = {}
    with np.load(packet_path, allow_pickle=False) as packet_archive:
        if "__task43_record_json__" not in packet_archive.files:
            raise ValueError("V16 P8 primary packet lacks its embedded identity")
        packet_embedded = json.loads(
            np.asarray(packet_archive["__task43_record_json__"], dtype=np.uint8)
            .tobytes()
            .decode("utf-8")
        )
        if (
            packet_embedded.get("schema") != "task43.v16.p8.primary_state.v1"
            or packet_embedded.get("identity") != primary_packet.get("identity")
            or packet_embedded.get("arrays") != primary_packet.get("arrays")
        ):
            raise ValueError("V16 P8 primary packet embedded identity differs from terminal")
        declared_arrays = primary_packet.get("arrays", {})
        if set(packet_archive.files) != set(declared_arrays) | {"__task43_record_json__"}:
            raise ValueError("V16 P8 primary packet member inventory differs")
        checkpoint_metadata = primary_packet.get("identity", {}).get(
            "pre_validation_checkpoint", {}
        )
        checkpoint_declared_arrays = checkpoint_metadata.get("arrays", {})
        if not isinstance(checkpoint_declared_arrays, Mapping) or not checkpoint_declared_arrays:
            raise ValueError("V16 P8 primary does not bind its pre-validation arrays")
        checkpoint_packet_keys = {
            "recovered_" + str(name) for name in checkpoint_declared_arrays
        }
        needed_packet_keys = (
            raw_keys
            | set(mesh_packet_keys.values())
            | checkpoint_packet_keys
            | {"recovered_recovered_p6_local_coefficients"}
        )
        if not needed_packet_keys.issubset(packet_archive.files):
            raise ValueError("V16 P8 primary packet omits required raw or recovery arrays")
        for name in needed_packet_keys:
            values = np.asarray(packet_archive[name]).copy()
            actual = _checkpoint_array_identity(values)
            declared = declared_arrays.get(name, {})
            if any(actual.get(key) != declared.get(key) for key in ("dtype", "shape", "sha256")):
                raise ValueError(f"V16 P8 primary array identity differs: {name}")
            loaded_arrays[name] = values
    prevalidation_array_identities = _v16_p8_read_and_bind_prevalidation_checkpoint(
        packet_path,
        primary_packet,
        prevalidation_npz_path,
        prevalidation_json_path,
        expected_primary_sha256=product_before["primary_packet"],
        expected_checkpoint_sha256=product_before["prevalidation_checkpoint"],
        expected_record_sha256=product_before["prevalidation_record"],
    )
    for name, identity in prevalidation_array_identities.items():
        packet_values = loaded_arrays.get("recovered_" + name)
        if packet_values is None or _checkpoint_array_identity(packet_values) != identity:
            raise ValueError(f"V16 P8 loaded primary array differs from checkpoint: {name}")
    endpoint_identity_packet = primary_packet.get("identity", {})
    if (
        endpoint_identity_packet.get("phase") != "R9_P8"
        or endpoint_identity_packet.get("contract_sha256") != contract_sha256
        or endpoint_identity_packet.get("candidate_identity") != candidate_identity
        or endpoint_identity_packet.get("space_source_binding") != terminal.get("space_source_binding")
        or endpoint_identity_packet.get("endpoint_identity") != endpoint_identity
        or raw_checkpoint.get("identity", {}).get("primary_packet") != primary_packet
    ):
        raise ValueError("V16 P8 embedded primary identity differs from its endpoint binding")
    actual_space = endpoint.get("preassembly_space_audit", {}).get("actual_space", {})
    raw_scope = endpoint_identity_packet.get("raw_full_active_scope", {})
    a6_scope = endpoint_identity_packet.get("independent_A6_raw_vector_scope", {})
    normal_audit = endpoint_identity_packet.get("normal_correction_audit", {})
    correction_ksp = normal_audit.get("correction_ksp", {})
    recomputed_raw = _v11_raw_vector_gates(
        loaded_arrays,
        active_trace_rows=int(actual_space.get("independent_trace_rows", -1)),
        active_interior_rows=int(actual_space.get("independent_cell_interior_rows", -1)),
        independent_fe_dofs=int(endpoint.get("independent_active_fe_dofs", -1)),
        active_full_rows=int(raw_scope.get("active_full_rows", -1)),
        full_active_scope=raw_scope,
        independent_a6_scope=a6_scope,
        normal_correction_count=int(endpoint_identity_packet.get("normal_correction_count", -1)),
        normal_converged_reason=int(correction_ksp.get("converged_reason", -1)),
        normal_correction_status=str(normal_audit.get("status", "")),
        extra_correction_count=int(endpoint_identity_packet.get("extra_correction_count", -1)),
    )
    if recomputed_raw.get("pass") is not True or raw_gate.get("gates") != recomputed_raw.get("gates"):
        raise ValueError("V16 P8 raw residual gates fail independent C recomputation")

    for name, path in lifecycle_paths.items():
        if _sha256_file(path) != product_before[name]:
            raise RuntimeError(f"V16 P8 F input changed during C validation: {name}")
    current_contract_inputs = (
        _v16_p8_input_snapshot(contract, additional_inputs=extra_inputs)
        if extra_inputs is not None
        else _v16_p8_input_snapshot(contract)
    )
    if current_contract_inputs != contract_inputs:
        raise RuntimeError("V16 P8 contract inputs changed during C first-read validation")
    if _verify_v16_p8_source_snapshot(space_binding) != space_binding["input_snapshot"]:
        raise RuntimeError("V16 P8 selected S source changed during C first-read validation")
    return {
        "contract": contract,
        "contract_sha256": contract_sha256,
        "execution_recovery": execution_recovery,
        "source_id": source_id,
        "run_root": run_root,
        "launch_root": launch_root,
        "space_binding": space_binding,
        "joined_terminal": joined,
        "terminal": terminal,
        "endpoint": endpoint,
        "endpoint_identity": endpoint_identity,
        "primary_packet": primary_packet,
        "primary_packet_arrays": loaded_arrays,
        "prevalidation_array_identities": prevalidation_array_identities,
        "raw_gate": recomputed_raw,
        "modal_payload": modal_payload,
        "modal_orders_path": orders_path,
        "p5_comparison": old_comparison,
        "lifecycle_paths": lifecycle_paths,
        "lifecycle_snapshot": product_before,
        "contract_input_snapshot": contract_inputs,
        "source_snapshot": source_snapshot,
    }


def _v16_require_saved_metrics_match(
    expected: Any, actual: Any, *, context: str
) -> None:
    """Cross-check saved P5 metrics against the same metrics recomputed here."""

    if isinstance(expected, Mapping):
        if not isinstance(actual, Mapping) or set(expected) != set(actual):
            raise ValueError(f"{context} mapping fields differ from the saved P5 value")
        for key in expected:
            _v16_require_saved_metrics_match(
                expected[key], actual[key], context=f"{context}.{key}"
            )
        return
    if isinstance(expected, (list, tuple)):
        if not isinstance(actual, (list, tuple)) or len(expected) != len(actual):
            raise ValueError(f"{context} sequence layout differs from the saved P5 value")
        for index, (expected_item, actual_item) in enumerate(
            zip(expected, actual, strict=True)
        ):
            _v16_require_saved_metrics_match(
                expected_item, actual_item, context=f"{context}[{index}]"
            )
        return
    if isinstance(expected, bool) or isinstance(actual, bool):
        if expected is not actual:
            raise ValueError(f"{context} boolean differs from the saved P5 value")
        return
    if expected is None or actual is None:
        if expected is not actual:
            raise ValueError(f"{context} nullability differs from the saved P5 value")
        return
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        if not np.isclose(float(expected), float(actual), rtol=1.0e-10, atol=1.0e-14):
            raise ValueError(f"{context} numeric value differs from the saved P5 value")
        return
    if expected != actual:
        raise ValueError(f"{context} differs from the saved P5 value")


def _restore_v16_p8_field(frozen: Mapping[str, Any]) -> dict[str, Any]:
    from benchmarks.task43_hp_adaptivity.h100_anchor import _h100_config
    from benchmarks.task43_hp_adaptivity.round1_candidates import _v16_p8_mesh_boxes

    endpoint = frozen["endpoint"]
    run_root = Path(frozen["run_root"])
    plan_path = run_root / "candidate_plan.json"
    plan = _json(plan_path)
    cfg = _h100_config(
        kind="empty_h_active_p3",
        case_name=str(endpoint["resolved_config"]["case_name"]),
        geometry_profile="initial_180",
    )
    cfg.stage4_local_h_refinement_plan = str(plan_path)
    mesh_data = build_stage4_local_h_mesh_data(cfg, plan_path, comm=MPI.COMM_WORLD)
    mesh = mesh_data.mesh
    axes = base._axes_from_mesh(mesh)
    plan_sha256 = _sha256_file(plan_path)
    actual_mesh_profile = _assert_mesh_profile(
        mesh_data,
        axes,
        "candidate_initial180",
        candidate_plan=plan,
        candidate_plan_sha256=plan_sha256,
    )
    if actual_mesh_profile != endpoint.get("numerical_controls", {}).get("mesh"):
        raise ValueError("V16 P8 restored mesh differs from the primary endpoint")
    space = _create_nedelec_space(mesh, cfg)
    actual_arrays = base._actual_mesh_identity(mesh, space)
    packet_arrays = frozen["primary_packet_arrays"]
    for identity_name, packet_name in {
        **{
            key: "recovered_" + key
            for key in (
                "mesh_geometry_coordinates_nm",
                "mesh_geometry_dofmap",
                "mesh_owned_cell_global_ids",
                "mesh_cell_vertex_dofmap",
                "p6_owned_global_dof_block_ids",
                "p6_ghost_global_dof_block_ids",
            )
        },
        "p6_function_space_cell_dofmap": "recovered_p6_function_space_dofmap",
    }.items():
        expected = packet_arrays[packet_name]
        actual = np.asarray(actual_arrays[identity_name])
        if (
            actual.dtype != expected.dtype
            or actual.shape != expected.shape
            or not np.array_equal(actual, expected)
        ):
            raise ValueError(f"V16 P8 restored mesh/DOF array differs from primary: {identity_name}")
    coefficients = packet_arrays["recovered_recovered_p6_local_coefficients"]
    if coefficients.dtype != np.dtype(np.complex128) or coefficients.shape != space.dofmap.index_map.local_to_global(
        np.arange(space.dofmap.index_map.size_local, dtype=np.int32)
    ).shape:
        raise ValueError("V16 P8 recovered full-carrier coefficient shape differs from live P6 space")
    field = fem.Function(space, name="v16_r9_p8_recovered_E")
    if field.x.array.shape != coefficients.shape:
        raise ValueError("V16 P8 recovered coefficient storage differs from local function array")
    field.x.array[:] = coefficients
    field.x.scatter_forward()
    boxes_storage = {
        "mesh_owned_cell_global_ids": actual_arrays["mesh_owned_cell_global_ids"],
        "mesh_geometry_coordinates_nm": actual_arrays["mesh_geometry_coordinates_nm"],
        "mesh_geometry_dofmap": actual_arrays["mesh_geometry_dofmap"],
    }
    ids, lower, upper = _v16_p8_mesh_boxes(boxes_storage)
    mode_payload = frozen["modal_payload"]
    power_metrics = mode_payload["metrics"]
    power = {
        "R_total": float(power_metrics["R_total"]),
        "T_total": float(power_metrics["T_total"]),
        "A_volume": float(endpoint["power"]["A_volume_total"]),
        "R00_s": float(power_metrics["R00_s"]),
        "R00_p": float(power_metrics["R00_p"]),
        "R00_total": float(power_metrics["R00_total"]),
    }
    return {
        "label": "R9_P8",
        "candidate_id": "v16_r9_p8",
        "cfg": cfg,
        "mesh_data": mesh_data,
        "field": field,
        "axes": axes,
        "record": endpoint,
        "mode_payload": mode_payload,
        "power": power,
        "mesh_identity": {
            name: base._array_identity(values) for name, values in actual_arrays.items()
        },
        "mesh_boxes": {"global_ids": ids, "lower": lower, "upper": upper},
        "actual_arrays": actual_arrays,
        "coefficients_identity": _checkpoint_array_identity(coefficients),
    }


def compare_v16_p8_paired(
    candidate_run_root: Path,
    accepted_parent_selection_record: Path,
    *,
    contract_path: Path,
    attempt_id: str,
    execution_recovery_path: Path | None = None,
) -> dict[str, Any]:
    """Reuse the fixed P5 R9/H8/Y6 arrays and sample restored P8 exactly once per q."""

    if MPI.COMM_WORLD.size != 1:
        raise RuntimeError("V16 P8 paired comparison is fixed to MPI1")
    contract_path = Path(contract_path).resolve()
    if execution_recovery_path is None:
        frozen = _v16_p8_frozen_endpoint(
            contract_path, Path(accepted_parent_selection_record).resolve()
        )
    else:
        frozen = _v16_p8_frozen_endpoint(
            contract_path,
            Path(accepted_parent_selection_record).resolve(),
            execution_recovery_path=execution_recovery_path,
        )
    from benchmarks.task43_hp_adaptivity import round1_candidates

    if attempt_id != frozen["contract"]["comparison"]["attempt_id"]:
        raise ValueError("V16 P8 comparison attempt id differs from the fixed contract")
    if Path(candidate_run_root).resolve() != Path(frozen["run_root"]).resolve():
        raise ValueError("V16 P8 comparison candidate root differs from the fixed F endpoint")
    contract = frozen["contract"]
    execution_recovery = frozen.get("execution_recovery")
    output_root = (
        round1_candidates._v18_p8_phase_root(execution_recovery, "C")
        / "comparison"
        if execution_recovery is not None
        else (
            Path(str(contract["artifact_prefix"]))
            / str(contract["comparison"]["output_root"])
        ).resolve()
    )
    if output_root.exists():
        raise FileExistsError(f"refusing to overwrite V16 P8 comparison root: {output_root}")
    runtime_environment = _check_v11_runtime_envelope(MPI.COMM_WORLD)
    worker_identity = runtime_environment["v11_watchdog_worker_identity"]
    source_start = _v11_source_snapshot()
    source_start[contract_path.relative_to(ROOT).as_posix()] = frozen["contract_sha256"]
    output_root.mkdir(parents=True, exist_ok=False)
    ledger = WorkflowLedger(output_root, Path(worker_identity["phase_path"]))
    started = time.perf_counter()
    samples_complete: dict[str, Any] = {}
    result_path = output_root / "v16_r9_p8_paired_comparison.json"
    progress_path = output_root / "comparison_progress.json"
    ledger.set_phase("preflight")
    ledger.marker(
        "task43_v16_p8_comparison_worker_bound",
        {
            "runtime_environment": runtime_environment,
            "worker_identity": worker_identity,
            "contract_sha256": frozen["contract_sha256"],
            "source_id": frozen["source_id"],
            "P5_input_sha256": frozen["contract_input_snapshot"],
        },
    )
    try:
        p8 = _restore_v16_p8_field(frozen)
        p5 = frozen["p5_comparison"]
        roles = {str(item["role"]): item for item in contract["inputs"]}
        r9_record = _json(ROOT / roles["R9_candidate_record"]["path"])
        h8_absorption = _json(ROOT / roles["H8_volume_absorption"]["path"])
        r9_orders = _json(ROOT / roles["R9_modal_orders"]["path"])
        h8_orders = _json(ROOT / roles["H8_modal_orders"]["path"])
        y6_orders = _json(ROOT / roles["Y6_1_modal_orders"]["path"])
        y6_restore_identity = _json(ROOT / roles["Y6_1_restore_identity"]["path"])
        y6_config = _json(ROOT / roles["Y6_1_resolved_config"]["path"])
        with np.load(
            ROOT / roles["H8_P4_primary_packet"]["path"], allow_pickle=False
        ) as h8_packet_archive:
            h8_packet_embedded = json.loads(
                np.asarray(
                    h8_packet_archive["__task43_record_json__"], dtype=np.uint8
                ).tobytes().decode("utf-8")
            )
        h8_actual_cfg = h8_packet_embedded["identity"]["endpoint_identity"][
            "actual_cfg"
        ]
        r9_cfg = _h100_config(
            kind="empty_h_active_p3",
            case_name=str(r9_record["resolved_config"]["case_name"]),
            geometry_profile="initial_180",
        )
        h8_cfg = _h100_config(
            kind="empty_h_active_p3",
            case_name=str(h8_actual_cfg["case_name"]),
            geometry_profile="initial_180",
        )
        y6_resolved = y6_restore_identity["resolved_identity"]
        y6_quadrature = y6_resolved["quadrature_and_cutoff"]
        y6_inventory_identity = {
            "axis_values_nm": y6_resolved["mesh_axes_nm"],
            "surface_q": int(y6_quadrature["surface_and_incident_degree"]),
            "volume_q": [
                {
                    "quadrature_degree": int(y6_quadrature["volume_degree"]),
                    "quadrature_rule": str(y6_quadrature["volume_rule"]),
                }
            ] * 2,
            "cutoff": str(y6_quadrature["cutoff_policy"]),
            "residuals": {
                "dtn_sparse_cutoff_relative_tolerance": float(
                    y6_quadrature["cutoff_relative_tolerance"]
                )
            },
        }
        y6_cfg = base._configure_historical_direct_route(
            y6_config, y6_inventory_identity
        )
        r9_power = {
            key: float(value)
            for key, value in {
                "R_total": r9_record["power"]["aggregate"]["R_total"],
                "T_total": r9_record["power"]["aggregate"]["T_total"],
                "A_volume": r9_record["power"]["A_volume_total"],
                "R00_s": r9_record["power"]["aggregate"]["R00_s"],
                "R00_p": r9_record["power"]["aggregate"]["R00_p"],
                "R00_total": r9_record["power"]["aggregate"]["R00_total"],
            }.items()
        }
        y6_restore_identity = _json(ROOT / roles["Y6_1_restore_identity"]["path"])
        y6_power = base._scalar_power_record(
            "Y6_1", y6_restore_identity, y6_orders
        )
        h8_power = {
            key: float(h8_orders["metrics"][key])
            for key in ("R_total", "T_total", "R00_s", "R00_p", "R00_total")
        }
        h8_power["A_volume"] = float(h8_absorption["A_volume_total"])
        for order in ("q8", "q10"):
            for label, actual in (("R9", r9_power), ("R9_H8", h8_power)):
                signed = p5["results"][order][label]["signed_observables"][
                    "aggregate_signed_candidate_minus_reference"
                ]
                expected_y6 = {
                    key: actual[key] - float(signed[key])
                    for key in ("R_total", "T_total", "A_volume", "R00_s", "R00_p", "R00_total")
                }
                if any(
                    not np.isclose(expected_y6[key], y6_power[key], rtol=0.0, atol=1.0e-12)
                    for key in expected_y6
                ):
                    raise ValueError(f"V16 P8 P5 {order}/{label} signed powers differ from saved modal/Av records")
        cases = {
            "R9": {
                "label": "R9",
                "cfg": r9_cfg,
                "mode_payload": r9_orders,
                "power": r9_power,
                "record": r9_record,
            },
            "R9_H8": {
                "label": "R9_H8",
                "cfg": h8_cfg,
                "mode_payload": h8_orders,
                "power": h8_power,
                "record": h8_packet_embedded["identity"]["endpoint_identity"],
            },
            "Y6_1": {
                "label": "Y6_1",
                "cfg": y6_cfg,
                "mode_payload": y6_orders,
                "power": y6_power,
                "record": y6_restore_identity,
            },
            "R9_P8": p8,
        }
        modal_physics = base._validate_mode_physics(
            cases, labels=("R9", "R9_H8", "Y6_1", "R9_P8")
        )
        full_mode_physics = {
            label: _post_selection_full_mode_physics(cases[label])
            for label in ("R9", "R9_H8", "Y6_1", "R9_P8")
        }
        expected_physics = p5["same_physics"]["shared_identity"]
        actual_physics = {
            label: base._physical_configuration_identity(cases[label]["cfg"])
            for label in ("R9", "R9_H8", "Y6_1", "R9_P8")
        }
        if any(identity != expected_physics for identity in actual_physics.values()):
            raise ValueError("V16 P8 reconstructed four-case configurations differ from P5 physics")
        common_physics = {
            "source": "P5 frozen shared identity cross-checked against four reconstructed configs",
            "shared_identity": expected_physics,
            "all_four_cases_match": True,
        }
        actual_fe = int(frozen["endpoint"]["independent_active_fe_dofs"])
        r9_fe = int(r9_record["recovered_solution_storage"]["independent_active_fe_dofs"])
        h8_fe = int(p5["actual_FE"]["R9_H8"])
        if actual_fe <= r9_fe or h8_fe <= r9_fe:
            raise ValueError("V16 P8 and H8 efficiency comparisons require positive measured Delta_FE")
        old_sample_entries = p5["saved_union_samples"]
        for order in ("q8", "q10"):
            ledger.set_phase(f"sample_{order}")
            old_sample_path = Path(str(old_sample_entries[order]["path"])).resolve()
            old_sample_sha256 = _sha256_file(old_sample_path)
            expected_old = roles[f"V15_P5_{order}_union_npz"]
            if old_sample_sha256 != expected_old["sha256"]:
                raise RuntimeError(f"V16 P8 P5 q{order} sample changed before read")
            with np.load(old_sample_path, allow_pickle=False) as archive:
                sample_record = json.loads(
                    np.asarray(archive["__task43_record_json__"], dtype=np.uint8)
                    .tobytes()
                    .decode("utf-8")
                )
                identity = sample_record.get("identity", {})
                if (
                    sample_record.get("schema") != "task43.v11.union_comparison_samples.v1"
                    or sample_record.get("official_result") is not False
                    or sample_record.get("passed") is not False
                    or int(identity.get("quadrature_order", -1))
                    != int(order.removeprefix("q"))
                    or identity.get("p4_original_terminal_status") != "FAILED"
                ):
                    raise ValueError(f"V16 P8 P5 q{order} archive identity differs")
                points = np.asarray(archive["points_nm"], dtype=np.float64).copy()
                weights = np.asarray(archive["weights_nm3"], dtype=np.float64).copy()
                old_samples = {
                    label: {
                        "E": np.asarray(archive[f"{label}_E"], dtype=np.complex128).copy(),
                        "curl_E": np.asarray(archive[f"{label}_curl_E"], dtype=np.complex128).copy(),
                    }
                    for label in ("R9", "R9_H8", "Y6_1")
                }
            if (
                points.shape != (int(expected_old["sample_count"]), 3)
                or weights.shape != (points.shape[0],)
                or not np.isfinite(points).all()
                or not np.isfinite(weights).all()
                or np.any(weights <= 0.0)
                or not np.isclose(
                    float(np.sum(weights, dtype=np.float64)),
                    350000.0,
                    rtol=0.0,
                    atol=1.0e-8,
                )
                or base._array_identity(points)["sha256"] != expected_old["point_sha256"]
                or base._array_identity(weights)["sha256"] != expected_old["weight_sha256"]
                or any(
                    fields["E"].shape != (points.shape[0], 3)
                    or fields["curl_E"].shape != (points.shape[0], 3)
                    or not np.isfinite(fields["E"]).all()
                    or not np.isfinite(fields["curl_E"]).all()
                    for fields in old_samples.values()
                )
            ):
                raise ValueError(f"V16 P8 P5 q{order} points, weights or saved fields are invalid")
            p8_samples = _sample_field(p8, points)
            if any(not np.isfinite(value).all() for value in p8_samples.values()):
                raise ValueError(f"V16 P8 q{order} restored field samples are nonfinite")
            p8_global_ids, p8_slots = base._cell_slot_for_points(
                p8["mesh_data"].mesh, p8["axes"], points
            )
            boxes = p8["mesh_boxes"]
            if (
                p8_slots.shape != (points.shape[0],)
                or p8_global_ids.shape != boxes["global_ids"].shape
                or not np.array_equal(p8_global_ids, boxes["global_ids"])
                or np.any(p8_slots < 0)
                or np.any(p8_slots >= p8_global_ids.size)
                or not np.array_equal(p8_global_ids[p8_slots], boxes["global_ids"][p8_slots])
                or not np.all(points >= boxes["lower"][p8_slots] - 1.0e-12)
                or not np.all(points <= boxes["upper"][p8_slots] + 1.0e-12)
            ):
                raise ValueError(f"V16 P8 q{order} sample owners are inconsistent with actual cell boxes")
            p8_owner_ids = p8_global_ids[p8_slots]
            p8_sample_arrays = {
                "P8_E": np.asarray(p8_samples["E"]),
                "P8_curl_E": np.asarray(p8_samples["curl_E"]),
                "P8_cell_global_ids": np.asarray(p8_global_ids),
                "P8_point_cell_local_slots": np.asarray(p8_slots),
                "P8_point_cell_global_ids": np.asarray(p8_owner_ids),
            }
            p8_sample_path = output_root / f"v16_r9_p8_{order}_samples.npz"
            p8_sample_record = write_atomic_npz(
                p8_sample_path,
                p8_sample_arrays,
                schema="task43.v16.p8.paired-sample.v1",
                classification="measured_P8_only_sample_reusing_hash_bound_P5_points",
                identity={
                    "contract_sha256": frozen["contract_sha256"],
                    "F_terminal_sha256": frozen["lifecycle_snapshot"]["terminal"],
                    "F_primary_packet_sha256": frozen["lifecycle_snapshot"]["primary_packet"],
                    "P5_sample_path": str(old_sample_path),
                    "P5_sample_sha256": old_sample_sha256,
                    "quadrature_order": int(order.removeprefix("q")),
                    "sample_count": int(points.shape[0]),
                    "point_identity": base._array_identity(points),
                    "weight_identity": base._array_identity(weights),
                    "old_fields_resampled": False,
                    "P8_sampled_once": True,
                    "candidate_identity": frozen["terminal"]["candidate_identity"],
                    "mesh_identity": p8["mesh_identity"],
                },
            )
            recomputed_old_results: dict[str, dict[str, Any]] = {}
            for label in ("R9", "R9_H8"):
                old_field_metrics = base._field_metrics(
                    old_samples["Y6_1"],
                    old_samples[label],
                    points,
                    weights,
                    cases["Y6_1"]["cfg"],
                )
                old_modal_metrics = base._modal_comparison(
                    cases["Y6_1"], cases[label]
                )
                old_j = _j_infinity(old_modal_metrics, old_field_metrics)
                old_signed = _v11_signed_mode_differences(
                    cases["Y6_1"], cases[label]
                )
                recomputed = {
                    "reference_label": "Y6_1",
                    "candidate_label": label,
                    "modal_metrics": old_modal_metrics,
                    "field_metrics": old_field_metrics,
                    "J_infinity": old_j,
                    "eta": float(
                        old_field_metrics["G"]["relative_with_incident_floor"]
                    ),
                    "signed_observables": old_signed,
                }
                expected_result = p5["results"][order].get(label)
                if not isinstance(expected_result, Mapping):
                    raise ValueError(
                        f"V16 P8 original P5 {order}/{label} result is missing"
                    )
                _v16_require_saved_metrics_match(
                    expected_result, recomputed, context=f"P5.{order}.{label}"
                )
                recomputed_old_results[label] = recomputed
            p8_case_samples = p8_samples
            modal_metrics = base._modal_comparison(cases["Y6_1"], cases["R9_P8"])
            signed = _v11_signed_mode_differences(cases["Y6_1"], cases["R9_P8"])
            field_metrics = base._field_metrics(
                old_samples["Y6_1"], p8_case_samples, points, weights, p8["cfg"]
            )
            score = _j_infinity(modal_metrics, field_metrics)
            eta_p8 = float(field_metrics["G"]["relative_with_incident_floor"])
            r9_result = recomputed_old_results["R9"]
            h8_result = recomputed_old_results["R9_H8"]
            eps_j = float(contract["comparison"]["epsilon_J"])
            eps_g = float(contract["comparison"]["epsilon_G"])
            classification = _v11_fixed_h_classification(
                j_r9=float(r9_result["J_infinity"]["value"]),
                j_h=float(score["value"]),
                eta_r9=float(r9_result["eta"]),
                eta_h=eta_p8,
                epsilon_j=eps_j,
                epsilon_g=eps_g,
            )
            delta_fe_p8 = actual_fe - r9_fe
            delta_fe_h8 = h8_fe - r9_fe
            h8_classification = _v11_fixed_h_classification(
                j_r9=float(r9_result["J_infinity"]["value"]),
                j_h=float(h8_result["J_infinity"]["value"]),
                eta_r9=float(r9_result["eta"]),
                eta_h=float(h8_result["eta"]),
                epsilon_j=eps_j,
                epsilon_g=eps_g,
            )
            p8_interval = {
                "point_estimate": classification["Delta_J"] / delta_fe_p8,
                "lower": (classification["Delta_J"] - eps_j) / delta_fe_p8,
                "upper": (classification["Delta_J"] + eps_j) / delta_fe_p8,
                "Delta_J_per_added_FE_dof": classification["Delta_J"] / delta_fe_p8,
                "Delta_G_per_added_FE_dof": classification["Delta_G"] / delta_fe_p8,
            }
            h8_interval = {
                "point_estimate": h8_classification["Delta_J"] / delta_fe_h8,
                "lower": (h8_classification["Delta_J"] - eps_j) / delta_fe_h8,
                "upper": (h8_classification["Delta_J"] + eps_j) / delta_fe_h8,
                "Delta_J_per_added_FE_dof": h8_classification["Delta_J"] / delta_fe_h8,
                "Delta_G_per_added_FE_dof": h8_classification["Delta_G"] / delta_fe_h8,
            }
            efficiency_order = {
                "P8": {**p8_interval, "Delta_FE": delta_fe_p8},
                "H8": {**h8_interval, "Delta_FE": delta_fe_h8},
                "P8_lower_exceeds_H8_upper": bool(p8_interval["lower"] > h8_interval["upper"]),
                "ranking_qualified": bool(
                    classification["positive_condition_pass"]
                    and eta_p8 <= float(r9_result["eta"]) + eps_g
                    and p8_interval["lower"] > h8_interval["upper"]
                ),
            }
            p8_result = {
                "reference_label": "Y6_1",
                "candidate_label": "R9_P8",
                "modal_metrics": modal_metrics,
                "field_metrics": field_metrics,
                "J_infinity": score,
                "eta": eta_p8,
                "signed_observables": signed,
                "P8_vs_R9": classification,
                "efficiency_per_added_FE": efficiency_order,
                "sample": {
                    "path": p8_sample_record["npz_path"],
                    "sha256": p8_sample_record["npz_sha256"],
                    "P5_sample_path": str(old_sample_path),
                    "P5_sample_sha256": old_sample_sha256,
                    "old_fields_resampled": False,
                    "P8_sampled_once": True,
                    "sample_count": int(points.shape[0]),
                },
            }
            samples_complete[order] = {
                **recomputed_old_results,
                "Y6_1_reference": {
                    "power": dict(y6_power),
                    "saved_field_source": str(old_sample_path),
                    "reference": True,
                },
                "R9_P8": p8_result,
                "classification": classification,
                "efficiency_per_added_FE": efficiency_order,
                "P8_FE": actual_fe,
                "R9_FE": r9_fe,
                "H8_FE": h8_fe,
            }
            old_sample_digest_after = _sha256_file(old_sample_path)
            if old_sample_digest_after != old_sample_sha256:
                raise RuntimeError(f"V16 P8 P5 q{order} sample changed during reuse")
            write_atomic_json(
                progress_path,
                {
                    "schema": "task43.v16.p8.paired-comparison-progress.v1",
                    "status": "Q8_COMPLETE_Q10_PENDING" if order == "q8" else "Q8_Q10_COMPLETE",
                    "results": samples_complete,
                    "official_result": False,
                    "passed": False,
                    "selection_eligible": False,
                    "continuation_all_false": True,
                },
                refuse_overwrite=False,
            )
            _require_v11_watchdog_worker_identity(
                expected_identity=worker_identity, require_unused_phase_file=False
            )
        q_classifications = [
            samples_complete[order]["classification"]["classification"]
            for order in ("q8", "q10")
        ]
        final_classification = (
            "SAMPLING_SENSITIVITY_UNRESOLVED"
            if q_classifications[0] != q_classifications[1]
            else q_classifications[0]
        )
        both_orders_ranking_qualified = all(
            samples_complete[order]["efficiency_per_added_FE"]["ranking_qualified"]
            for order in ("q8", "q10")
        )
        for order in ("q8", "q10"):
            samples_complete[order]["efficiency_per_added_FE"][
                "both_orders_ranking_qualified"
            ] = bool(both_orders_ranking_qualified)
            samples_complete[order]["both_orders_ranking_qualified"] = bool(
                both_orders_ranking_qualified
            )
        source_end = _v11_source_snapshot()
        source_end[contract_path.relative_to(ROOT).as_posix()] = frozen["contract_sha256"]
        execution_inputs = (
            {
                execution_recovery["manifest_path"]: execution_recovery[
                    "manifest_sha256"
                ],
                execution_recovery["tracked_summary_path"]: execution_recovery[
                    "tracked_summary_sha256"
                ],
                execution_recovery["test_terminal_path"]: execution_recovery[
                    "test_terminal_sha256"
                ],
                execution_recovery["test_qualification_path"]: execution_recovery[
                    "test_qualification_sha256"
                ],
                execution_recovery["test_root_observation_path"]: execution_recovery[
                    "test_root_observation_sha256"
                ],
                execution_recovery["runtime_identity_path"]: execution_recovery[
                    "runtime_identity_sha256"
                ],
                execution_recovery["launch_script_path"]: execution_recovery[
                    "launch_script_sha256"
                ],
            }
            if execution_recovery is not None
            else None
        )
        inputs_end = (
            round1_candidates._v16_p8_input_snapshot(
                contract, additional_inputs=execution_inputs
            )
            if execution_inputs is not None
            else round1_candidates._v16_p8_input_snapshot(contract)
        )
        if (
            source_end != source_start
            or inputs_end != frozen["contract_input_snapshot"]
            or _verify_v16_p8_source_snapshot(frozen["space_binding"])
            != frozen["space_binding"]["input_snapshot"]
        ):
            raise RuntimeError("V16 P8 source or input identity changed during paired comparison")
        for name, path in frozen["lifecycle_paths"].items():
            if _sha256_file(path) != frozen["lifecycle_snapshot"][name]:
                raise RuntimeError(f"V16 P8 F product changed during paired comparison: {name}")
        record = {
            "schema": "task43.v16.p8.paired-comparison.v1",
            "status": "COMPLETE_DIAGNOSTIC_NOT_ACCEPTANCE",
            "classification": final_classification,
            "qualification_boundary": "same-point four-field fixed-reference output response only; no selection/transition",
            "official_result": False,
            "passed": False,
            "selection_eligible": False,
            "selection_candidate": False,
            "candidate_selected": False,
            "continuation_all_false": True,
            "attempt_id": attempt_id,
            "contract_path": str(contract_path),
            "contract_sha256": frozen["contract_sha256"],
            "execution_recovery_binding": (
                {
                    "path": execution_recovery["manifest_path"],
                    "sha256": execution_recovery["manifest_sha256"],
                    "phase": "C",
                }
                if execution_recovery is not None
                else None
            ),
            "fixed_reference": "Y6_1",
            "candidate_id": "v16_r9_p8",
            "original_P4_status": "FAILED",
            "F_joined_terminal_path": str(frozen["lifecycle_paths"]["joined"].resolve()),
            "F_joined_terminal_sha256": frozen["lifecycle_snapshot"]["joined"],
            "F_terminal_path": str(frozen["lifecycle_paths"]["terminal"].resolve()),
            "F_terminal_sha256": frozen["lifecycle_snapshot"]["terminal"],
            "F_endpoint_path": str(frozen["lifecycle_paths"]["endpoint"].resolve()),
            "F_endpoint_sha256": frozen["lifecycle_snapshot"]["endpoint"],
            "F_primary_packet_sha256": frozen["lifecycle_snapshot"]["primary_packet"],
            "P5_comparison_path": str(ROOT / roles["V15_P5_comparison_record"]["path"]),
            "P5_comparison_sha256": roles["V15_P5_comparison_record"]["sha256"],
            "P5_old_samples_resampled": False,
            "source_identity_start": source_start,
            "source_identity_end": source_end,
            "contract_input_identity_start": frozen["contract_input_snapshot"],
            "contract_input_identity_end": inputs_end,
            "shared_physics": common_physics,
            "modal_physics": modal_physics,
            "full_612_physical_reconstruction": full_mode_physics,
            "modal_count": 612,
            "FE": {"R9": r9_fe, "H8": h8_fe, "P8": actual_fe, "Delta_FE_P8": actual_fe - r9_fe, "Delta_FE_H8": h8_fe - r9_fe},
            "epsilon_J": float(contract["comparison"]["epsilon_J"]),
            "epsilon_G": float(contract["comparison"]["epsilon_G"]),
            "results": samples_complete,
            "both_orders_ranking_qualified": bool(both_orders_ranking_qualified),
            "wall_seconds": time.perf_counter() - started,
        }
        write_atomic_json(result_path, record)
        ledger.set_phase("complete")
        ledger.marker("task43_v16_p8_paired_comparison_complete", {"record": str(result_path), "classification": final_classification})
        return record
    except BaseException as error:
        failure = {
            "schema": "task43.v16.p8.paired-comparison-failure.v1",
            "status": "FAILED_AFTER_Q8_PRESERVED" if "q8" in samples_complete else "FAILED_BEFORE_Q8",
            "classification": "ACTION_ENDPOINT_NOT_QUALIFIED",
            "error": f"{type(error).__name__}: {error}",
            "completed_q_orders": list(samples_complete),
            "completed_results": samples_complete,
            "official_result": False,
            "passed": False,
            "selection_eligible": False,
            "continuation_all_false": True,
            "contract_sha256": frozen["contract_sha256"],
            "F_joined_terminal_sha256": frozen["lifecycle_snapshot"]["joined"],
        }
        write_atomic_json(output_root / "v16_r9_p8_comparison_failure.json", failure)
        try:
            ledger.set_phase("failed")
            ledger.marker("task43_v16_p8_paired_comparison_failed", failure)
        except BaseException:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-run-root", type=Path)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--accepted-parent-selection-record", type=Path)
    parser.add_argument("--post-selection-record", type=Path)
    parser.add_argument("--assets-manifest", type=Path)
    parser.add_argument("--validation-reference-root", type=Path)
    parser.add_argument("--diagnostic-contract", type=Path)
    parser.add_argument("--execution-recovery-manifest", type=Path)
    parser.add_argument("--saved-primary-recovery-binding", type=Path)
    parser.add_argument("--paired-p8-contract", type=Path)
    parser.add_argument("--p8-execution-recovery-binding", type=Path)
    args = parser.parse_args()
    if not args.attempt_id or Path(args.attempt_id).name != args.attempt_id:
        parser.error("--attempt-id must be one path component")
    if args.paired_p8_contract is not None:
        if (
            args.candidate_run_root is None
            or args.accepted_parent_selection_record is None
            or args.diagnostic_contract is not None
            or args.execution_recovery_manifest is not None
            or args.saved_primary_recovery_binding is not None
            or args.post_selection_record is not None
            or args.assets_manifest is not None
            or args.validation_reference_root is not None
        ):
            parser.error(
                "V16 P8 paired comparison requires its F run and accepted R9 selection, and rejects other modes"
            )
        compare_kwargs = {
            "contract_path": args.paired_p8_contract,
            "attempt_id": args.attempt_id,
        }
        if args.p8_execution_recovery_binding is not None:
            compare_kwargs["execution_recovery_path"] = (
                args.p8_execution_recovery_binding
            )
        result = compare_v16_p8_paired(
            args.candidate_run_root.resolve(),
            args.accepted_parent_selection_record.resolve(),
            **compare_kwargs,
        )
        print(
            json.dumps(
                {
                    "stage": "v16_p8_paired_comparison_complete",
                    "classification": result["classification"],
                    "record": str(
                        Path(str(result["results"]["q10"]["R9_P8"]["sample"]["path"]))
                        .parent
                        / "v16_r9_p8_paired_comparison.json"
                    ),
                    "q8": result["results"]["q8"]["classification"]["classification"],
                    "q10": result["results"]["q10"]["classification"]["classification"],
                },
                sort_keys=True,
                allow_nan=False,
            ),
            flush=True,
        )
    elif args.p8_execution_recovery_binding is not None:
        parser.error("--p8-execution-recovery-binding requires --paired-p8-contract")
    elif args.diagnostic_contract is not None:
        if (
            args.candidate_run_root is None
            or args.accepted_parent_selection_record is None
            or args.execution_recovery_manifest is None
            or args.post_selection_record is not None
            or args.assets_manifest is not None
            or args.validation_reference_root is not None
        ):
            parser.error(
                "V11 diagnostic mode requires P4 candidate and accepted R9 paths and rejects post-selection arguments"
            )
        result = compare_v11_union(
            args.candidate_run_root.resolve(),
            args.accepted_parent_selection_record.resolve(),
            contract_path=args.diagnostic_contract,
            recovery_manifest_path=args.execution_recovery_manifest,
            attempt_id=args.attempt_id,
            saved_primary_recovery_binding_path=args.saved_primary_recovery_binding,
        )
        print(
            json.dumps(
                {
                    "stage": "v11_union_comparison_complete",
                    "classification": result["classification"],
                    "record": str(
                        Path(str(result["saved_union_samples"]["q10"]["path"]))
                        .parent
                        / "v11_r9_h8_union_comparison.json"
                    ),
                    "Delta_J": result["q10_primary_classification"]["Delta_J"],
                    "Delta_G": result["q10_primary_classification"]["Delta_G"],
                },
                sort_keys=True,
                allow_nan=False,
            ),
            flush=True,
        )
    elif (
        args.execution_recovery_manifest is not None
        or args.saved_primary_recovery_binding is not None
    ):
        parser.error(
            "recovery bindings require their matching diagnostic mode"
        )
    elif args.post_selection_record is not None:
        if (args.candidate_run_root is not None or args.accepted_parent_selection_record is not None
                or args.assets_manifest is None or args.validation_reference_root is None):
            parser.error("post-selection mode requires assets/reference roots and rejects adaptive arguments")
        compare_post_selection(args.post_selection_record, args.assets_manifest,
                               args.validation_reference_root, DEFAULT_OUTPUT / args.attempt_id)
    else:
        if (args.candidate_run_root is None or args.assets_manifest is not None
                or args.validation_reference_root is not None):
            parser.error("adaptive mode requires candidate root and rejects post-selection arguments")
        compare_candidate(args.candidate_run_root.resolve(), DEFAULT_OUTPUT / args.attempt_id,
                          args.accepted_parent_selection_record)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
