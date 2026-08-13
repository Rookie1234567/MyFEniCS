"""Private Task38 worker contract and resolved-payload dispatch."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from src.io.execution_plan import (
    CONTRACT_PROBE_ADAPTER,
    method_adapter_identity,
)
from src.io.input_loader import InputError
from src.io.input_validation import task039_07nm_launch_error, task039_model_id_matches


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
    return parser


def _dispatch_resolved_payload(
    resolved_payload: dict[str, Any],
    *,
    expected_method: str,
    output_directory: Path,
    expected_source_sha: str | None = None,
    expected_resolved_config_sha256: str | None = None,
    task039_trace_audit: bool = False,
) -> tuple[int, list[str]]:
    """Dispatch the already validated payload without rereading its input."""

    pending_07nm = task039_07nm_launch_error(resolved_payload)
    if pending_07nm is not None:
        return 4, [pending_07nm]

    if expected_method in {"2d_scattered", "2d_port"}:
        from src.runners.task038_2d import run_2d

        adapter = run_2d
        label = "2D"
    elif expected_method == "full3d_direct":
        from src.runners.task038_full3d_direct import run_full3d_direct

        adapter = run_full3d_direct
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
