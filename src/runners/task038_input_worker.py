"""Private Task38 worker contract and resolved-payload dispatch."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from src.io.execution_plan import (
    CONTRACT_PROBE_ADAPTER,
    method_adapter_identity,
)
from src.io.input_loader import InputError
from src.io.input_validation import (
    TASK42_13P5_FULL3D_MODEL_ID,
    TASK42_DIRECT_FACTOR_LIFECYCLE,
    task039_07nm_launch_error,
    task039_model_id_matches,
)

TASK42_STAGED_DIRECT_BRIDGE_PATH_ENV = "TASK42_STAGED_DIRECT_BRIDGE_PATH"


def _task42_inventory_json_bytes(value: Any) -> bytes:
    """Encode the small scalar inventory accepted by Task42 stage receipts."""

    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Task42 stage inventory is not finite JSON data: {exc}"
        ) from exc


def _task42_stage_gate_callback(
    *, output_directory: Path, comm: Any, root_pid: int
):
    """Create a rank-consistent phase gate using the launcher's whole-job root."""

    from benchmarks.task034_wsl_resources import resource_authority_sample
    from src.io.input_validation import task42_memory_gate_from_authority

    if type(root_pid) is not int or root_pid <= 0:
        raise ValueError("Task42 stage gate requires a positive launcher root PID")
    samples_path = (
        Path(output_directory).resolve()
        / "numerical_output"
        / "task42_stage_resource_gates.jsonl"
    )
    path_state = None
    if comm.rank == 0:
        path_state = {
            "exists": samples_path.exists(),
            "path": str(samples_path),
        }
    path_state = comm.bcast(path_state, root=0)
    if not isinstance(path_state, dict) or path_state.get("exists") is not False:
        raise RuntimeError(
            "Task42 stage gate refuses an existing or unverified phase receipt"
        )
    writer_started = False

    def gate(stage: str, local_delta_bytes: int, inventory: dict[str, Any]):
        nonlocal writer_started
        local_errors: list[str] = []
        if not isinstance(stage, str) or not stage.strip():
            local_errors.append("stage_identity_is_missing")
        if type(local_delta_bytes) is not int or local_delta_bytes < 0:
            local_errors.append("local_Delta_must_be_a_nonnegative_exact_integer")
        if not isinstance(inventory, dict):
            local_errors.append("inventory_must_be_a_mapping")
            components = None
        else:
            components = inventory.get("components")
            if not isinstance(components, list) or not components:
                local_errors.append("inventory_components_are_missing")
                components = None
        local_component_bytes = 0
        component_names: list[str] = []
        if components is not None:
            for index, component in enumerate(components):
                if not isinstance(component, dict):
                    local_errors.append(f"inventory_component_{index}_is_not_a_mapping")
                    continue
                name = component.get("name")
                scope = component.get("scope")
                amount = component.get("delta_bytes")
                if not isinstance(name, str) or not name.strip():
                    local_errors.append(f"inventory_component_{index}_name_is_invalid")
                else:
                    component_names.append(name)
                if scope not in ("rank_local", "global_replicated"):
                    local_errors.append(f"inventory_component_{index}_scope_is_invalid")
                if component.get("unit") != "bytes":
                    local_errors.append(f"inventory_component_{index}_unit_is_not_bytes")
                if type(amount) is not int or amount < 0:
                    local_errors.append(
                        f"inventory_component_{index}_delta_bytes_is_invalid"
                    )
                elif scope == "rank_local":
                    local_component_bytes += amount
            if len(component_names) != len(set(component_names)):
                local_errors.append("inventory_component_names_are_not_unique")
        if (
            type(local_delta_bytes) is int
            and local_delta_bytes >= 0
            and local_component_bytes != local_delta_bytes
        ):
            local_errors.append("rank_local_inventory_differs_from_gate_argument")
        if isinstance(inventory, dict):
            try:
                _task42_inventory_json_bytes(inventory)
            except ValueError as exc:
                local_errors.append(str(exc))
        local_row = {
            "rank": int(comm.rank),
            "stage": stage if isinstance(stage, str) else None,
            "local_delta_bytes": (
                local_delta_bytes if type(local_delta_bytes) is int else None
            ),
            "inventory": inventory if isinstance(inventory, dict) else None,
            "errors": local_errors,
        }
        rank_rows = comm.allgather(local_row)
        stage_names = {row.get("stage") for row in rank_rows}
        errors = [
            f"rank_{row.get('rank')}_{error}"
            for row in rank_rows
            for error in row.get("errors", [])
        ]
        if len(stage_names) != 1:
            errors.append("MPI_ranks_requested_different_stage_names")
        local_deltas = [row.get("local_delta_bytes") for row in rank_rows]
        if any(type(value) is not int or value < 0 for value in local_deltas):
            errors.append("MPI_rank_Delta_inventory_is_incomplete")
        rank_component_rows: list[dict[str, dict[str, Any]]] = []
        expected_component_names: tuple[str, ...] | None = None
        for row in rank_rows:
            row_inventory = row.get("inventory")
            row_components = (
                row_inventory.get("components")
                if isinstance(row_inventory, dict)
                else None
            )
            by_name: dict[str, dict[str, Any]] = {}
            if not isinstance(row_components, list):
                errors.append(f"rank_{row.get('rank')}_inventory_components_are_missing")
            else:
                for component in row_components:
                    if isinstance(component, dict) and isinstance(
                        component.get("name"), str
                    ):
                        by_name[component["name"]] = component
            names = tuple(sorted(by_name))
            if expected_component_names is None:
                expected_component_names = names
            elif names != expected_component_names:
                errors.append("MPI_ranks_reported_different_Delta_components")
            rank_component_rows.append(by_name)
        component_aggregation: dict[str, dict[str, Any]] = {}
        phase_delta: int | None = None
        if expected_component_names is not None:
            phase_delta = 0
            for name in expected_component_names:
                entries = [row.get(name) for row in rank_component_rows]
                if any(not isinstance(entry, dict) for entry in entries):
                    errors.append(f"MPI_component_{name}_is_missing_on_a_rank")
                    continue
                scopes = {entry.get("scope") for entry in entries if entry is not None}
                units = {entry.get("unit") for entry in entries if entry is not None}
                values = [entry.get("delta_bytes") for entry in entries if entry is not None]
                if len(scopes) != 1 or len(units) != 1:
                    errors.append(f"MPI_component_{name}_scope_or_unit_differs")
                    continue
                scope = next(iter(scopes))
                if units != {"bytes"} or any(
                    type(value) is not int or value < 0 for value in values
                ):
                    errors.append(f"MPI_component_{name}_value_or_unit_is_invalid")
                    continue
                if scope == "rank_local":
                    amount = sum(values)
                    aggregation = "sum_rank_local_values"
                elif scope == "global_replicated":
                    if len(set(values)) != 1:
                        errors.append(f"replicated_global_component_{name}_differs")
                        continue
                    amount = values[0]
                    aggregation = "count_one_replicated_global_value"
                else:
                    errors.append(f"MPI_component_{name}_scope_is_invalid")
                    continue
                phase_delta += amount
                component_aggregation[name] = {
                    "scope": scope,
                    "unit": "bytes",
                    "rank_values_bytes": values,
                    "counted_bytes": amount,
                    "aggregation": aggregation,
                }
        result = None
        if comm.rank == 0:
            authority = None
            gate_record = None
            if not errors and type(phase_delta) is int:
                try:
                    authority = resource_authority_sample(root_pid)
                    gate_record = task42_memory_gate_from_authority(
                        authority,
                        expected_root_pid=root_pid,
                        phase_additional_bytes=phase_delta,
                    )
                except BaseException as exc:  # noqa: BLE001 - rank-0 local refusal must reach the following broadcast
                    errors.append(
                        f"phase_authority_sample_failed:{type(exc).__name__}:{exc}"
                    )
            passed = bool(
                not errors
                and isinstance(gate_record, dict)
                and gate_record.get("pass") is True
            )
            record = {
                "schema": "task42.direct_phase_gate_receipt.v1",
                "phase": next(iter(stage_names)) if len(stage_names) == 1 else None,
                "decision": "allow" if passed else "refuse",
                "rank_inventory": rank_rows,
                "phase_additional_bytes": phase_delta,
                "phase_delta_unit": "bytes",
                "phase_delta_aggregation": component_aggregation,
                "authority": authority,
                "gate": gate_record,
                "errors": errors,
            }
            try:
                samples_path.parent.mkdir(parents=True, exist_ok=True)
                mode = "a" if writer_started else "x"
                with samples_path.open(mode, encoding="utf-8") as stream:
                    stream.write(
                        json.dumps(
                            record,
                            sort_keys=True,
                            separators=(",", ":"),
                            allow_nan=False,
                        )
                        + "\n"
                    )
                    stream.flush()
                writer_started = True
            except BaseException as exc:  # noqa: BLE001 - local writer refusal is synchronized below
                errors.append(
                    f"phase_receipt_write_failed:{type(exc).__name__}:{exc}"
                )
                passed = False
            result = {
                "pass": passed,
                "decision": "allow" if passed else "refuse",
                "phase": record["phase"],
                "phase_additional_bytes": phase_delta,
                "gate": gate_record,
                "errors": errors,
                "receipt_path": str(samples_path),
            }
        result = comm.bcast(result, root=0)
        if not isinstance(result, dict) or type(result.get("pass")) is not bool:
            raise RuntimeError("Task42 phase gate returned no unanimous receipt")
        return result

    return gate


def _read_json_bytes(
    path: Path, label: str
) -> tuple[dict[str, Any] | None, bytes | None, str | None]:
    try:
        payload = path.read_bytes()
        value = json.loads(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, None, f"{label} is unreadable: {exc}"
    if not isinstance(value, dict):
        return None, payload, f"{label} must contain a JSON object"
    return value, payload, None


def _load_and_validate_worker_payload(
    *,
    resolved_config: str | Path,
    manifest: str | Path,
    expected_input_sha256: str,
    expected_physical_model_sha256: str,
    expected_source_sha: str,
    expected_mpi_size: int,
    expected_method: str,
    expected_adapter: str,
    expected_output_directory: str | Path,
    expected_resolved_config_sha256: str,
    actual_mpi_size: int,
    contract_probe: bool = False,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Read each contract JSON once and return the validated resolved payload."""

    resolved_path = Path(resolved_config)
    manifest_path = Path(manifest)
    expected_output_path = Path(expected_output_directory).resolve()
    errors: list[str] = []
    resolved, resolved_bytes, resolved_error = _read_json_bytes(
        resolved_path, "resolved config"
    )
    manifest_value, _manifest_bytes, manifest_error = _read_json_bytes(
        manifest_path, "manifest"
    )
    if resolved_error:
        errors.append(resolved_error)
    if manifest_error:
        errors.append(manifest_error)
    if resolved is None or resolved_bytes is None or manifest_value is None:
        return None, errors

    resolved_sha = hashlib.sha256(resolved_bytes).hexdigest()
    if resolved_sha != expected_resolved_config_sha256:
        errors.append("resolved config SHA does not match the launch contract")

    if resolved_path.resolve().parent != expected_output_path:
        errors.append("resolved config output directory mismatch")
    if manifest_path.resolve().parent != expected_output_path:
        errors.append("manifest output directory mismatch")

    provenance = resolved.get("provenance")
    if not isinstance(provenance, dict):
        errors.append("resolved config provenance is missing")
    else:
        if provenance.get("input_sha256") != expected_input_sha256:
            errors.append("resolved config input SHA mismatch")
        if provenance.get("physical_model_sha256") != expected_physical_model_sha256:
            errors.append("resolved config physical model SHA mismatch")

        if provenance.get("source_path") != manifest_value.get("input_path"):
            errors.append("manifest input path mismatch")

    input_copy = expected_output_path / "input_original.dat"
    try:
        input_copy_bytes = input_copy.read_bytes()
    except OSError as exc:
        errors.append(f"input_original.dat is unreadable: {exc}")
    else:
        input_copy_sha = hashlib.sha256(input_copy_bytes).hexdigest()
        if input_copy_sha != expected_input_sha256:
            errors.append("input_original.dat SHA mismatch")
        if input_copy_sha != manifest_value.get("input_sha256"):
            errors.append("input_original.dat manifest SHA mismatch")

    method_payload = resolved.get("method")
    if not isinstance(method_payload, dict):
        errors.append("resolved config method payload is missing")
        method = None
        requested_modes = None
    else:
        method = method_payload.get("kind")
        requested_modes = method_payload.get("requested_modes_per_direction")
    if method != expected_method:
        errors.append("resolved config method mismatch")

    execution_payload = resolved.get("execution")
    if not isinstance(execution_payload, dict):
        errors.append("resolved config execution payload is missing")
    elif execution_payload.get("mpi_size") != expected_mpi_size:
        errors.append("resolved config MPI size mismatch")

    try:
        expected_method_adapter = method_adapter_identity(
            expected_method,
            str(resolved.get("model_id", "")),
        )
    except InputError:
        expected_method_adapter = None
    if contract_probe != (expected_adapter == CONTRACT_PROBE_ADAPTER):
        errors.append("contract-probe mode and adapter identity mismatch")
    if expected_adapter == CONTRACT_PROBE_ADAPTER:
        pass
    elif expected_method_adapter is None or expected_adapter != expected_method_adapter:
        errors.append("adapter identity mismatch with expected method")

    if actual_mpi_size != expected_mpi_size:
        errors.append("MPI.COMM_WORLD size mismatch")
    if manifest_value.get("mpi_size") != expected_mpi_size:
        errors.append("manifest MPI size mismatch")
    if manifest_value.get("method") != expected_method:
        errors.append("manifest method mismatch")
    if manifest_value.get("resolved_method_adapter") != expected_adapter:
        errors.append("manifest adapter identity mismatch")
    if manifest_value.get("input_sha256") != expected_input_sha256:
        errors.append("manifest input SHA mismatch")
    if manifest_value.get("physical_model_sha256") != expected_physical_model_sha256:
        errors.append("manifest physical model SHA mismatch")
    if manifest_value.get("source_sha") != expected_source_sha:
        errors.append("manifest source SHA mismatch")
    if manifest_value.get("resolved_config_sha256") != resolved_sha:
        errors.append("manifest resolved config SHA mismatch")
    if manifest_value.get("output_directory") != str(expected_output_path):
        errors.append("manifest output directory mismatch")
    if manifest_value.get("numerical_output_directory") != str(
        expected_output_path / "numerical_output"
    ):
        errors.append("manifest numerical output directory mismatch")

    for identity_key in ("model_id", "run_id", "comparison_group"):
        if manifest_value.get(identity_key) != resolved.get(identity_key):
            errors.append(f"manifest {identity_key.replace('_', ' ')} mismatch")
    if manifest_value.get("solver") != resolved.get("solver"):
        errors.append("manifest solver payload mismatch")
    if manifest_value.get("requested_modes") != requested_modes:
        errors.append("manifest requested-mode identity mismatch")
    return resolved, errors


def validate_worker_contract(**kwargs: Any) -> list[str]:
    """Validate worker identity without reading the original .dat."""

    _resolved, errors = _load_and_validate_worker_payload(**kwargs)
    return errors


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="private Task38 worker contract")
    parser.add_argument("--resolved-config", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--expected-input-sha256", required=True)
    parser.add_argument("--expected-physical-model-sha256", required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--expected-mpi-size", type=int, required=True)
    parser.add_argument("--expected-method", required=True)
    parser.add_argument("--expected-adapter", required=True)
    parser.add_argument("--expected-output-directory", type=Path, required=True)
    parser.add_argument("--resolved-config-sha256", required=True)
    parser.add_argument("--contract-probe", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--task039-trace-audit", action="store_true", help=argparse.SUPPRESS
    )
    parser.add_argument(
        "--task42-packet-recovery-manifest",
        type=Path,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--task42-packet-recovery-manifest-sha256",
        help=argparse.SUPPRESS,
    )
    return parser


def _dispatch_resolved_payload(
    resolved_payload: dict[str, Any],
    *,
    expected_method: str,
    output_directory: Path,
    expected_source_sha: str | None = None,
    expected_resolved_config_sha256: str | None = None,
    task039_trace_audit: bool = False,
    task42_packet_recovery_manifest: Path | None = None,
    task42_packet_recovery_manifest_sha256: str | None = None,
    task42_packet_recovery_archive_source_sha: str | None = None,
    task42_packet_recovery_archive_resolved_config_sha256: str | None = None,
    task42_packet_recovery_output_probes: Mapping[str, Any] | None = None,
    comm: Any | None = None,
) -> tuple[int, list[str]]:
    """Dispatch the already validated payload without rereading its input."""

    if (task42_packet_recovery_manifest is None) != (
        task42_packet_recovery_manifest_sha256 is None
    ):
        return 4, ["Task42 recovery manifest and SHA must be supplied together"]
    if task42_packet_recovery_manifest is None and (
        task42_packet_recovery_archive_source_sha is not None
        or task42_packet_recovery_archive_resolved_config_sha256 is not None
        or task42_packet_recovery_output_probes is not None
    ):
        return 4, ["Task42 archive identity/output overrides require a packet recovery"]

    pending_07nm = task039_07nm_launch_error(resolved_payload)
    if pending_07nm is not None:
        return 4, [pending_07nm]

    if expected_method in {"2d_scattered", "2d_port"}:
        from src.runners.task038_2d import run_2d

        adapter = run_2d
        label = "2D"
    elif expected_method == "full3d_direct":
        from src.runners.task038_full3d_direct import run_full3d_direct

        def adapter(payload, directory):
            solver_payload = payload.get("solver", {})
            task42_direct = (
                payload.get("model_id") == TASK42_13P5_FULL3D_MODEL_ID
                and solver_payload.get("direct_factor_lifecycle")
                == TASK42_DIRECT_FACTOR_LIFECYCLE
            )
            if task42_direct:
                if comm is None:
                    raise RuntimeError("Task42 direct worker is missing MPI communicator")
                root_pid_text = os.environ.get("TASK038_JOB_ROOT_PID")
                bridge_path = os.environ.get(
                    TASK42_STAGED_DIRECT_BRIDGE_PATH_ENV
                )
                local_binding = {
                    "root_pid": root_pid_text,
                    "bridge_path": bridge_path,
                    "output_directory": str(Path(directory).resolve()),
                    "packet_recovery_manifest": (
                        None
                        if task42_packet_recovery_manifest is None
                        else str(task42_packet_recovery_manifest.resolve())
                    ),
                    "packet_recovery_manifest_sha256": (
                        task42_packet_recovery_manifest_sha256
                    ),
                    "packet_recovery_archive_source_sha": (
                        task42_packet_recovery_archive_source_sha
                    ),
                    "packet_recovery_archive_resolved_config_sha256": (
                        task42_packet_recovery_archive_resolved_config_sha256
                    ),
                    "packet_recovery_output_probes": (
                        None
                        if task42_packet_recovery_output_probes is None
                        else dict(task42_packet_recovery_output_probes)
                    ),
                }
                bindings = comm.allgather(local_binding)
                if len({_task42_inventory_json_bytes(row) for row in bindings}) != 1:
                    raise RuntimeError(
                        "Task42 direct worker root/bridge/output binding differs across MPI ranks"
                    )
                try:
                    root_pid = int(root_pid_text) if root_pid_text is not None else 0
                except ValueError as exc:
                    raise RuntimeError(
                        "Task42 direct worker root PID is not an integer"
                    ) from exc
                packet_recovery = task42_packet_recovery_manifest is not None
                if root_pid <= 0 or (not bridge_path and not packet_recovery):
                    raise RuntimeError(
                        "Task42 worker requires launcher root PID and either a staged bridge or packet-recovery binding"
                    )
                if packet_recovery and bridge_path:
                    raise RuntimeError(
                        "Task42 packet recovery cannot load or use the staged direct-factor bridge"
                    )
                stage_gate = _task42_stage_gate_callback(
                    output_directory=Path(directory),
                    comm=comm,
                    root_pid=root_pid,
                )
                return run_full3d_direct(
                    payload,
                    directory,
                    source_sha=expected_source_sha,
                    resolved_config_sha256=expected_resolved_config_sha256,
                    task42_stage_gate=stage_gate,
                    task42_bridge_path=bridge_path,
                    task42_packet_recovery_manifest=(
                        task42_packet_recovery_manifest
                    ),
                    task42_packet_recovery_manifest_sha256=(
                        task42_packet_recovery_manifest_sha256
                    ),
                    task42_packet_recovery_archive_source_sha=(
                        task42_packet_recovery_archive_source_sha
                    ),
                    task42_packet_recovery_archive_resolved_config_sha256=(
                        task42_packet_recovery_archive_resolved_config_sha256
                    ),
                    task42_packet_recovery_output_probes=(
                        task42_packet_recovery_output_probes
                    ),
                )
            if solver_payload.get("direct_factor_lifecycle") == "release_before_recovery":
                return run_full3d_direct(
                    payload,
                    directory,
                    source_sha=expected_source_sha,
                    resolved_config_sha256=expected_resolved_config_sha256,
                )
            return run_full3d_direct(payload, directory)

        label = "Full3D direct"
    elif expected_method == "full3d_iterative":
        from src.runners.task039_full3d_iterative import run_full3d_iterative

        def adapter(payload, directory):
            return run_full3d_iterative(
                payload,
                directory,
                source_sha=expected_source_sha,
            )

        label = "Full3D iterative"
    elif expected_method == "hybrid_direct":
        if task039_model_id_matches(
            "hybrid_direct", str(resolved_payload.get("model_id", ""))
        ):
            from src.runners.task039_hybrid_direct import run_task039_hybrid_direct

            def adapter(payload, directory):
                return run_task039_hybrid_direct(
                    payload,
                    directory,
                    source_sha=expected_source_sha,
                    trace_audit_capture_dir=(
                        directory / "numerical_output" / "task039_trace_audit"
                        if task039_trace_audit
                        else None
                    ),
                    trace_audit_metadata=(
                        {
                            "input_sha256": payload["provenance"]["input_sha256"],
                            "physical_model_sha256": payload["provenance"][
                                "physical_model_sha256"
                            ],
                            "resolved_config_sha256": expected_resolved_config_sha256,
                        }
                        if task039_trace_audit
                        else None
                    ),
                )

            label = "Task39 Hybrid direct"
        else:
            from src.runners.task038_hybrid_direct import run_hybrid_direct

            def adapter(payload, directory):
                return run_hybrid_direct(
                    payload,
                    directory,
                    source_sha=expected_source_sha,
                )

            label = "Hybrid direct"
    elif expected_method == "hybrid_iterative":
        if task039_model_id_matches(
            "hybrid_iterative", str(resolved_payload.get("model_id", ""))
        ):
            from src.runners.task039_hybrid_iterative import (
                run_task039_hybrid_iterative,
            )

            def adapter(payload, directory):
                return run_task039_hybrid_iterative(
                    payload,
                    directory,
                    source_sha=expected_source_sha,
                )

            label = "Task39 Hybrid iterative"
        else:
            from src.runners.task038_hybrid_iterative import run_hybrid_iterative

            def adapter(payload, directory):
                return run_hybrid_iterative(
                    payload,
                    directory,
                    source_sha=expected_source_sha,
                )

            label = "Hybrid iterative"
    else:
        return 3, [f"Task38 {expected_method} numerical adapter is unavailable"]

    try:
        result = adapter(resolved_payload, output_directory)
    except Exception as exc:  # convert one worker boundary failure to a nonzero exit
        return 4, [f"Task38 {label} adapter failed: {exc}"]
    if not result["passed"]:
        return 4, list(result["errors"])
    return 0, []


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        from mpi4py import MPI
    except ImportError as exc:
        raise SystemExit(f"Task38 worker requires mpi4py: {exc}") from exc
    comm = MPI.COMM_WORLD
    resolved_payload, errors = _load_and_validate_worker_payload(
        resolved_config=args.resolved_config,
        manifest=args.manifest,
        expected_input_sha256=args.expected_input_sha256,
        expected_physical_model_sha256=args.expected_physical_model_sha256,
        expected_source_sha=args.expected_source_sha,
        expected_mpi_size=args.expected_mpi_size,
        expected_method=args.expected_method,
        expected_adapter=args.expected_adapter,
        expected_output_directory=args.expected_output_directory,
        expected_resolved_config_sha256=args.resolved_config_sha256,
        actual_mpi_size=comm.size,
        contract_probe=args.contract_probe,
    )
    failed = comm.allreduce(bool(errors), op=MPI.LOR)
    if failed:
        if comm.rank == 0:
            for error in errors:
                print(f"Task38 worker contract error: {error}")
        return 2
    if args.task039_trace_audit and args.contract_probe:
        if comm.rank == 0:
            print(
                "Task039 trace audit cannot be combined with contract probe",
                flush=True,
            )
        return 2
    if args.task039_trace_audit and not task039_model_id_matches(
        "hybrid_direct",
        str(resolved_payload.get("model_id", "")),
        resolved_payload.get("method", {}).get("requested_modes_per_direction"),
    ):
        if comm.rank == 0:
            print(
                "Task039 trace audit requires hybrid_direct M=120/240/480/960",
                flush=True,
            )
        return 2
    recovery_manifest = args.task42_packet_recovery_manifest
    recovery_sha256 = args.task42_packet_recovery_manifest_sha256
    if (recovery_manifest is None) != (recovery_sha256 is None):
        if comm.rank == 0:
            print("Task42 packet recovery arguments must be supplied together")
        return 2
    if recovery_manifest is not None:
        solver = resolved_payload.get("solver", {})
        recovery_valid = bool(
            not args.contract_probe
            and resolved_payload.get("model_id") == TASK42_13P5_FULL3D_MODEL_ID
            and args.expected_method == "full3d_direct"
            and int(resolved_payload.get("execution", {}).get("mpi_size", -1)) == 8
            and solver.get("direct_factor_lifecycle")
            == TASK42_DIRECT_FACTOR_LIFECYCLE
            and recovery_manifest.is_absolute()
            and recovery_manifest.is_file()
            and isinstance(recovery_sha256, str)
            and len(recovery_sha256) == 64
            and all(character in "0123456789abcdef" for character in recovery_sha256)
        )
        recovery_valid = bool(comm.allreduce(recovery_valid, op=MPI.LAND))
        if not recovery_valid:
            if comm.rank == 0:
                print("Task42 packet recovery binding is invalid for this worker route")
            return 2
    if args.contract_probe:
        comm.Barrier()
        if comm.rank == 0:
            marker = args.expected_output_directory / "worker_contract_probe.json"
            marker.write_bytes(
                json.dumps(
                    {"status": "contract_probe_pass", "mpi_size": comm.size},
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                + b"\n"
            )
        return 0
    if resolved_payload is None:
        return 2
    exit_status, dispatch_errors = _dispatch_resolved_payload(
        resolved_payload,
        expected_method=args.expected_method,
        output_directory=args.expected_output_directory,
        expected_source_sha=args.expected_source_sha,
        expected_resolved_config_sha256=args.resolved_config_sha256,
        task039_trace_audit=args.task039_trace_audit,
        task42_packet_recovery_manifest=recovery_manifest,
        task42_packet_recovery_manifest_sha256=recovery_sha256,
        comm=comm,
    )
    if exit_status != 0:
        if comm.rank == 0:
            for error in dispatch_errors:
                print(f"Task38 {args.expected_method} authority error: {error}")
        return exit_status
    return exit_status


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main", "validate_worker_contract"]
