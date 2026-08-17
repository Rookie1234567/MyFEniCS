"""Thin V4 h4 mode-prep/direct-consumer orchestration.

The producer and consumer are separate MPI phases.  This module owns only the
hash-bound identity and phase argv; QEP, packet IO, and the augmented direct
solver remain in their existing implementations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Mapping

from benchmarks.run_task032_phase6_augmented import main as run_task032_main
from src.io.execution_plan import ExecutionPlan
from src.io.input_loader import InputError
from src.io.input_validation import (
    load_and_resolve,
    simulation_config_3d_from_normalized,
    task039_dynamic_external_mode_inventory,
    task039_model_id_matches,
    task039_profile_errors,
)
from src.io.resolved_config import resolved_config_sha256
from src.io.run_specification import RunSpecification
from src.runners.task039_hybrid_direct import (
    _append_source_attestation,
    _argv_for_payload,
    run_task039_hybrid_direct,
)


TASK039_V4_H4_HYBRID_DIRECT_INPUT = Path(
    "input/official/task039/5nm_p6h4_v4_1deg_hybrid_direct_m480_mpi8.dat"
)
TASK039_V4_H4_HYBRID_DIRECT_MODEL_ID = "task039_5nm_v4_1deg_s5_hybrid_direct_m480"
TASK039_V4_H4_MODE_SCOPE = "task039_v4_h4_m480"
TASK039_V4_H4_MPI_SIZE = 8
TASK039_V4_H4_MODE_COUNT = 480
TASK039_V4_H4_WARNING_MEMORY_GIB = 170.0
TASK039_V4_H4_CRITICAL_MEMORY_GIB = 195.0
TASK039_V4_H4_HARD_STOP_BYTES = 224_000_000_000
TASK039_V4_H4_POLL_SECONDS = 0.25
TASK039_V4_H4_ADAPTER_IDENTITY = "task039.v4.h4.hybrid_direct"


def _sha256_json(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_v4_h4_packet_manifest(manifest: str | Path, expected_sha256: str) -> str:
    """Verify the packet manifest before a direct phase is launched."""

    path = Path(manifest).resolve()
    if not path.is_file():
        raise InputError(f"V4 h4 packet manifest is missing: {path}")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected_sha256:
        raise InputError("V4 h4 packet manifest SHA256 does not match the plan")
    return actual


def _validate_source_sha(source_sha: str) -> str:
    if (
        len(source_sha) != 40
        or source_sha != source_sha.lower()
        or any(char not in "0123456789abcdef" for char in source_sha)
    ):
        raise InputError(
            "V4 h4 orchestration requires a lowercase 40-character source SHA"
        )
    return source_sha


def validate_v4_h4_specification(
    specification: RunSpecification,
) -> dict[str, Any]:
    """Validate the fixed h4/M480 scope and return its resolved payload."""

    payload = specification.as_jsonable()
    model_id = str(payload.get("model_id", ""))
    method = payload.get("method", {})
    discretization = payload.get("discretization", {})
    execution = payload.get("execution", {})
    if model_id != TASK039_V4_H4_HYBRID_DIRECT_MODEL_ID:
        raise InputError("V4 h4 Hybrid-direct requires the explicit model identity")
    if not task039_model_id_matches(
        "hybrid_direct", model_id, method.get("requested_modes_per_direction")
    ):
        raise InputError("V4 h4 Hybrid-direct model/M identity is not connected")
    errors = task039_profile_errors(payload)
    if errors:
        path, message = errors[0]
        raise InputError(f"{path}: {message}")
    if discretization.get("mesh_target_nm") != 4.0:
        raise InputError("V4 h4 Hybrid-direct requires mesh_target_nm=4.0")
    if method.get("requested_modes_per_direction") != TASK039_V4_H4_MODE_COUNT:
        raise InputError("V4 h4 Hybrid-direct requires M=480")
    if execution.get("mpi_size") != TASK039_V4_H4_MPI_SIZE:
        raise InputError("V4 h4 Hybrid-direct requires MPI8")
    inventory = task039_dynamic_external_mode_inventory(payload)
    keys = inventory.get("keys")
    if not isinstance(keys, list) or not keys:
        raise InputError("V4 h4 dynamic external inventory must be non-empty")
    if len({json.dumps(key, sort_keys=True) for key in keys}) != len(keys):
        raise InputError("V4 h4 dynamic external inventory keys must be unique")
    return payload


def build_v4_h4_mode_identity(
    specification: RunSpecification,
    source_sha: str,
) -> dict[str, Any]:
    """Build producer authority shared unchanged by both V4 consumers."""

    payload = validate_v4_h4_specification(specification)
    source = _validate_source_sha(source_sha)
    inventory = task039_dynamic_external_mode_inventory(payload)
    return {
        "schema": "task039.v4.h4.mode-identity.v1",
        "scope": TASK039_V4_H4_MODE_SCOPE,
        "method_independent": True,
        "source_sha": source,
        "input_sha256": specification.input_sha256,
        "resolved_sha256": resolved_config_sha256(specification),
        "physical_sha256": specification.physical_model_sha256,
        "model_id": payload["model_id"],
        "run_id": payload["run_id"],
        "comparison_group": payload["comparison_group"],
        "mesh": {
            "target_nm": payload["discretization"]["mesh_target_nm"],
            "nedelec_degree": payload["discretization"]["nedelec_degree"],
            "cell_type": payload["discretization"]["mesh_cell_type"],
        },
        "mode_count": TASK039_V4_H4_MODE_COUNT,
        "mpi_size": TASK039_V4_H4_MPI_SIZE,
        "external_keys": {
            "count": len(inventory["keys"]),
            "sha256": _sha256_json(inventory["keys"]),
        },
    }


def write_v4_h4_mode_identity(
    specification: RunSpecification,
    source_sha: str,
    target: str | Path,
) -> tuple[dict[str, Any], str]:
    """Write the shared identity JSON and return it with its file SHA256."""

    identity = build_v4_h4_mode_identity(specification, source_sha)
    path = Path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (
        json.dumps(identity, ensure_ascii=False, sort_keys=True, indent=2).encode(
            "utf-8"
        )
        + b"\n"
    )
    path.write_bytes(data)
    return identity, hashlib.sha256(data).hexdigest()


def _phase_argv(
    specification: RunSpecification,
    output_directory: str | Path,
    source_sha: str,
    phase: str,
    *,
    identity_json: str | Path,
    packet_directory: str | Path | None = None,
    manifest: str | Path | None = None,
    manifest_sha256: str | None = None,
) -> list[str]:
    payload = validate_v4_h4_specification(specification)
    output = Path(output_directory).resolve() / "numerical_output" / "run_summary.json"
    argv = _append_source_attestation(_argv_for_payload(payload, output), source_sha)
    if phase == "mode-prep":
        if packet_directory is None:
            raise InputError("mode-prep requires a packet directory")
        argv.extend(
            [
                "--selected-mode-packet-producer-dir",
                str(Path(packet_directory).resolve()),
                "--selected-mode-packet-identity-json",
                str(Path(identity_json).resolve()),
            ]
        )
    elif phase == "direct-consumer":
        if manifest is None or manifest_sha256 is None:
            raise InputError("direct-consumer requires manifest and manifest SHA256")
        argv.extend(
            [
                "--selected-mode-packet-consumer-manifest",
                str(Path(manifest).resolve()),
                "--selected-mode-packet-consumer-identity-json",
                str(Path(identity_json).resolve()),
                "--selected-mode-packet-consumer-manifest-sha256",
                manifest_sha256,
            ]
        )
    else:
        raise InputError(f"unknown V4 h4 phase {phase!r}")
    return argv


def build_v4_h4_phase_plan(
    specification: RunSpecification,
    run_directory: str | Path,
    source_sha: str,
    *,
    phase: str,
    identity_json: str | Path,
    packet_directory: str | Path | None = None,
    manifest: str | Path | None = None,
    manifest_sha256: str | None = None,
    python_executable: str | Path | None = None,
    mpiexec_command: str | None = None,
) -> ExecutionPlan:
    """Build the separate MPI8 worker command without starting it."""

    validate_v4_h4_specification(specification)
    if phase == "mode-prep" and packet_directory is None:
        raise InputError("mode-prep requires a packet directory")
    if phase == "direct-consumer" and (manifest is None or manifest_sha256 is None):
        raise InputError("direct-consumer requires manifest and manifest SHA256")
    if not Path(identity_json).is_file():
        raise InputError(f"V4 h4 mode identity is missing: {identity_json}")
    if phase == "direct-consumer":
        validate_v4_h4_packet_manifest(manifest, manifest_sha256)
    source = _validate_source_sha(source_sha)
    run_path = Path(run_directory).resolve()
    executable = Path(os.path.abspath(python_executable or sys.executable))
    mpiexec = mpiexec_command or shutil.which("mpiexec") or "mpiexec"
    worker_argv = [
        str(mpiexec),
        "-n",
        str(TASK039_V4_H4_MPI_SIZE),
        str(executable),
        "-m",
        "benchmarks.task039_v4_h4_hybrid_direct",
        "--worker",
        "--phase",
        phase,
        "--resolved-config",
        str(run_path / "resolved_config.json"),
        "--output-directory",
        str(run_path),
        "--source-sha",
        source,
        "--identity-json",
        str(Path(identity_json).resolve()),
    ]
    if packet_directory is not None:
        worker_argv.extend(
            ["--packet-directory", str(Path(packet_directory).resolve())]
        )
    if manifest is not None:
        worker_argv.extend(["--manifest", str(Path(manifest).resolve())])
    if manifest_sha256 is not None:
        worker_argv.extend(["--manifest-sha256", manifest_sha256])
    return ExecutionPlan(
        argv=tuple(worker_argv),
        shell=False,
        executable=executable,
        worker_module="benchmarks.task039_v4_h4_hybrid_direct",
        method="hybrid_direct",
        mpi_size=TASK039_V4_H4_MPI_SIZE,
        requested_modes=TASK039_V4_H4_MODE_COUNT,
        physical_model_sha256=specification.physical_model_sha256,
        input_sha256=specification.input_sha256,
        source_sha=source,
        adapter_identity=TASK039_V4_H4_ADAPTER_IDENTITY,
        adapter_available=True,
        contract_probe=False,
        task039_trace_audit=False,
        expected_output_directory=run_path,
        expected_resolved_config=run_path / "resolved_config.json",
        expected_manifest=run_path / "run_manifest.json",
    )


def launch_v4_h4_phase(
    specification: RunSpecification,
    run_directory: str | Path,
    source_sha: str,
    *,
    phase: str,
    identity_json: str | Path,
    packet_directory: str | Path | None = None,
    manifest: str | Path | None = None,
    manifest_sha256: str | None = None,
    python_executable: str | Path | None = None,
    mpiexec_command: str | None = None,
    poll_interval: float = TASK039_V4_H4_POLL_SECONDS,
) -> dict[str, Any]:
    """Launch one phase through the existing Task38 process-tree watchdog."""

    from src.runners.task038_launcher import (
        _now,
        _run_worker,
        _write_bootstrap,
    )
    from benchmarks.task034_wsl_resources import resource_authority_sample
    from benchmarks.watchdog_process_control import terminate_process_tree

    run_path = Path(run_directory).resolve()
    if run_path.exists():
        raise InputError(f"V4 h4 run directory already exists: {run_path}")
    run_path.mkdir(parents=True)
    manifest_value, resolved_sha = _write_bootstrap(
        specification,
        run_path,
        source_sha=_validate_source_sha(source_sha),
        adapter_identity=TASK039_V4_H4_ADAPTER_IDENTITY,
        start_time=_now(),
    )
    plan = build_v4_h4_phase_plan(
        specification,
        run_path,
        source_sha,
        phase=phase,
        identity_json=identity_json,
        packet_directory=packet_directory,
        manifest=manifest,
        manifest_sha256=manifest_sha256,
        python_executable=python_executable,
        mpiexec_command=mpiexec_command,
    )
    result = _run_worker(
        plan,
        specification,
        run_path,
        popen_factory=subprocess.Popen,
        sample_factory=resource_authority_sample,
        terminate_factory=terminate_process_tree,
        monotonic=time.monotonic,
        sleep=time.sleep,
        poll_interval=poll_interval,
    )
    manifest_value.update(
        {
            "status": "finished",
            "end_time": _now(),
            "exit_status": result.get("exit_status"),
            "result_classification": result.get("result_classification"),
            "resolved_config_sha256": resolved_sha,
        }
    )
    (run_path / "run_manifest.json").write_text(
        json.dumps(manifest_value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    summary = {
        "status": "finished",
        "run_directory": str(run_path),
        "resolved_config_sha256": resolved_sha,
        **result,
    }
    (run_path / "run_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def run_v4_h4_worker(
    resolved_config: str | Path,
    output_directory: str | Path,
    source_sha: str,
    *,
    phase: str,
    identity_json: str | Path,
    packet_directory: str | Path | None = None,
    manifest: str | Path | None = None,
    manifest_sha256: str | None = None,
) -> Mapping[str, Any]:
    """Execute one already-planned phase inside the MPI worker."""

    payload = json.loads(Path(resolved_config).read_text(encoding="utf-8"))
    specification = load_and_resolve(payload["provenance"]["source_path"])
    validate_v4_h4_specification(specification)
    if phase == "direct-consumer":
        if manifest is None or manifest_sha256 is None:
            raise InputError("direct-consumer requires manifest and manifest SHA256")
        validate_v4_h4_packet_manifest(manifest, manifest_sha256)
    if phase == "mode-prep":
        argv = _phase_argv(
            specification,
            output_directory,
            source_sha,
            phase,
            identity_json=identity_json,
            packet_directory=packet_directory,
        )
        return run_task032_main(
            argv,
            config_override=simulation_config_3d_from_normalized(payload),
            use_case080_reference=False,
            canonical_export_prefix="task039_v4_mode_prep",
            external_mode_inventory=task039_dynamic_external_mode_inventory(payload),
            exact_one_cell_work_dir=Path(output_directory)
            / "numerical_output"
            / "exact_one_cell",
            task039_stage_marker_path=Path(output_directory)
            / "numerical_output"
            / "memory_stage_markers.raw.jsonl",
        )
    if phase == "direct-consumer":
        return run_task039_hybrid_direct(
            payload,
            output_directory,
            source_sha=source_sha,
            selected_mode_packet_consumer_manifest=manifest,
            selected_mode_packet_consumer_identity_json=identity_json,
            selected_mode_packet_consumer_manifest_sha256=manifest_sha256,
        )
    raise InputError(f"unknown V4 h4 phase {phase!r}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--phase", choices=("mode-prep", "direct-consumer"), required=True
    )
    parser.add_argument("--resolved-config", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--identity-json", type=Path, required=True)
    parser.add_argument("--packet-directory", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--manifest-sha256")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.worker:
        raise SystemExit("the V4 h4 module is only a private worker")
    from mpi4py import MPI

    try:
        result = run_v4_h4_worker(
            args.resolved_config,
            args.output_directory,
            args.source_sha,
            phase=args.phase,
            identity_json=args.identity_json,
            packet_directory=args.packet_directory,
            manifest=args.manifest,
            manifest_sha256=args.manifest_sha256,
        )
        failed = not isinstance(result, Mapping) or result.get("passed") is False
    except Exception as exc:
        failed = True
        if MPI.COMM_WORLD.rank == 0:
            print(
                f"Task039 V4 h4 worker failed: {type(exc).__name__}: {exc}", flush=True
            )
    return 4 if MPI.COMM_WORLD.allreduce(failed, op=MPI.LOR) else 0


__all__ = [
    "TASK039_V4_H4_HYBRID_DIRECT_INPUT",
    "TASK039_V4_H4_HYBRID_DIRECT_MODEL_ID",
    "TASK039_V4_H4_MODE_SCOPE",
    "build_v4_h4_mode_identity",
    "build_v4_h4_phase_plan",
    "launch_v4_h4_phase",
    "main",
    "run_v4_h4_worker",
    "validate_v4_h4_packet_manifest",
    "validate_v4_h4_specification",
    "write_v4_h4_mode_identity",
]


if __name__ == "__main__":
    raise SystemExit(main())
