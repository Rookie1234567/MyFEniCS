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
TASK039_V4_H4_HYBRID_ITERATIVE_INPUT = Path(
    "input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat"
)
TASK039_V4_H4_HYBRID_DIRECT_MODEL_ID = "task039_5nm_v4_1deg_s5_hybrid_direct_m480"
TASK039_V4_H4_HYBRID_ITERATIVE_MODEL_ID = "task039_5nm_v4_1deg_s5_hybrid_iterative_m480"
TASK039_V4_H4_MODE_SCOPE = "task039_v4_h4_m480"
TASK039_V4_H4_MPI_SIZE = 8
TASK039_V4_H4_MODE_COUNT = 480
TASK039_V4_H4_WARNING_MEMORY_GIB = 170.0
TASK039_V4_H4_CRITICAL_MEMORY_GIB = 195.0
TASK039_V4_H4_HARD_STOP_BYTES = 224_000_000_000
TASK039_V4_H4_POLL_SECONDS = 0.25
TASK039_V4_H4_ADAPTER_IDENTITY = "task039.v4.h4.hybrid_direct"
TASK039_V4_H4_ITERATIVE_ADAPTER_IDENTITY = "task039.v4.h4.hybrid_iterative"
TASK039_V4_H4_QUALIFICATION_METHOD = "task039_v4_h4_exact_side_case_qualification"
TASK039_V4_H4_QUALIFICATION_TARGET = (
    "TASK039_V4_CASE_QUALIFIED_EXPLICIT_OPT_IN_HYBRID_ITERATIVE_EXACT_SIDE_PASS"
)
TASK039_V5_H5_HYBRID_DIRECT_INPUT = Path(
    "input/official/task039/5nm_p6h5_v3_1deg_hybrid_direct_m480_mpi8.dat"
)
TASK039_V5_H5_HYBRID_DIRECT_MODEL_ID = "task039_5nm_v3_1deg_s5_hybrid_direct_m480"
TASK039_V5_H5_MODE_SCOPE = "task039_v5_h5_m480"
TASK039_V5_H5_MPI_SIZE = 8
TASK039_V5_H5_MODE_COUNT = 480
TASK039_V5_H5_ADAPTER_IDENTITY = "task039.v5.h5.hybrid_direct"


def _sha256_json(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _v4_h4_packet_consumer_gate(
    qep_release: Mapping[str, Any],
    *,
    manifest_sha256: str,
    identity_sha256: str,
) -> bool:
    return bool(
        qep_release.get("qep_calls") == 0
        and qep_release.get("consumer_qep_required") is False
        and qep_release.get("packet_manifest_sha256") == manifest_sha256
        and qep_release.get("packet_identity_sha256") == identity_sha256
        and qep_release.get("packet_mmap_released") is True
        and qep_release.get("packet_references_released") is True
    )


def validate_v4_h4_packet_manifest(manifest: str | Path, expected_sha256: str) -> str:
    """Verify the packet manifest before a direct phase is launched."""

    path = Path(manifest).resolve()
    if not path.is_file():
        raise InputError(f"V4 h4 packet manifest is missing: {path}")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected_sha256:
        raise InputError("V4 h4 packet manifest SHA256 does not match the plan")
    return actual


def _validate_v4_h4_phase_method(specification: RunSpecification, phase: str) -> None:
    expected = "hybrid_iterative" if phase == "iterative-consumer" else "hybrid_direct"
    if specification.method.get("kind") != expected:
        raise InputError(f"V4 phase {phase!r} requires method.kind={expected!r}")


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
    if model_id not in {
        TASK039_V4_H4_HYBRID_DIRECT_MODEL_ID,
        TASK039_V4_H4_HYBRID_ITERATIVE_MODEL_ID,
    }:
        raise InputError("V4 h4 requires the explicit direct or iterative identity")
    kind = str(method.get("kind", ""))
    if not task039_model_id_matches(
        kind, model_id, method.get("requested_modes_per_direction")
    ):
        raise InputError("V4 h4 model/M identity is not connected")
    errors = task039_profile_errors(payload)
    if errors:
        path, message = errors[0]
        raise InputError(f"{path}: {message}")
    if discretization.get("mesh_target_nm") != 4.0:
        raise InputError("V4 h4 requires mesh_target_nm=4.0")
    if method.get("requested_modes_per_direction") != TASK039_V4_H4_MODE_COUNT:
        raise InputError("V4 h4 requires M=480")
    if execution.get("mpi_size") != TASK039_V4_H4_MPI_SIZE:
        raise InputError("V4 h4 requires MPI8")
    inventory = task039_dynamic_external_mode_inventory(payload)
    keys = inventory.get("keys")
    if not isinstance(keys, list) or not keys:
        raise InputError("V4 h4 dynamic external inventory must be non-empty")
    if len({json.dumps(key, sort_keys=True) for key in keys}) != len(keys):
        raise InputError("V4 h4 dynamic external inventory keys must be unique")
    return payload


def validate_v5_h5_specification(
    specification: RunSpecification,
) -> dict[str, Any]:
    """Validate the fixed V5-S h5 current-lifecycle sidecar profile."""

    payload = specification.as_jsonable()
    method = payload.get("method", {})
    incidence = payload.get("incidence", {})
    discretization = payload.get("discretization", {})
    execution = payload.get("execution", {})
    if payload.get("model_id") != TASK039_V5_H5_HYBRID_DIRECT_MODEL_ID:
        raise InputError("V5-S h5 requires the existing 1-degree h5 direct identity")
    if method.get("kind") != "hybrid_direct" or not task039_model_id_matches(
        "hybrid_direct",
        payload["model_id"],
        method.get("requested_modes_per_direction"),
    ):
        raise InputError("V5-S h5 requires a direct M480 model identity")
    errors = task039_profile_errors(payload)
    if errors:
        path, message = errors[0]
        raise InputError(f"{path}: {message}")
    fixed = (
        (payload.get("dimension"), 3, "dimension=3"),
        (incidence.get("wavelength_nm"), 5.0, "wavelength=5nm"),
        (incidence.get("grazing_angle_deg"), 1.0, "grazing=1 degree"),
        (incidence.get("azimuth_deg"), 0.0, "azimuth=0"),
        (incidence.get("polarization"), "s", "polarization=s"),
        (discretization.get("mesh_target_nm"), 5.0, "mesh=h5"),
        (discretization.get("nedelec_degree"), 6, "p6"),
        (method.get("bottom_interface_nm"), 10.0, "bottom interface=10nm"),
        (method.get("top_interface_nm"), 110.0, "top interface=110nm"),
        (method.get("requested_modes_per_direction"), 480, "M=480"),
        (execution.get("mpi_size"), TASK039_V5_H5_MPI_SIZE, "MPI8"),
        (execution.get("warning_memory_gib"), 170.0, "warning=170GiB"),
        (execution.get("terminate_memory_gib"), 195.0, "critical=195GiB"),
        (execution.get("absolute_terminate_memory_bytes"), 224000000000, "hard=224e9"),
        (execution.get("timeout_seconds"), 21600, "timeout=21600s"),
        (execution.get("require_zero_swap"), True, "swap=0"),
    )
    for actual, expected, label in fixed:
        if actual != expected:
            raise InputError(f"V5-S h5 requires {label}")
    inventory = task039_dynamic_external_mode_inventory(payload)
    keys = inventory.get("keys")
    if not isinstance(keys, list) or not keys:
        raise InputError("V5-S h5 external inventory must be non-empty")
    if len({json.dumps(key, sort_keys=True) for key in keys}) != len(keys):
        raise InputError("V5-S h5 external inventory keys must be unique")
    return payload


def _validate_v5_h5_phase_method(specification: RunSpecification, phase: str) -> None:
    if phase not in {"mode-prep", "direct-consumer"}:
        raise InputError("V5-S h5 supports only mode-prep and direct-consumer")
    if specification.method.get("kind") != "hybrid_direct":
        raise InputError("V5-S h5 phases require method.kind=hybrid_direct")


def build_v4_h4_mode_identity(
    specification: RunSpecification,
    source_sha: str,
    *,
    profile: str = "v4-h4",
) -> dict[str, Any]:
    """Build producer authority shared unchanged by both V4 consumers."""

    if profile == "v5-h5":
        payload = validate_v5_h5_specification(specification)
        scope = TASK039_V5_H5_MODE_SCOPE
        schema = "task039.v5.h5.mode-identity.v1"
        mode_count = TASK039_V5_H5_MODE_COUNT
        mpi_size = TASK039_V5_H5_MPI_SIZE
    elif profile == "v4-h4":
        payload = validate_v4_h4_specification(specification)
        scope = TASK039_V4_H4_MODE_SCOPE
        schema = "task039.v4.h4.mode-identity.v1"
        mode_count = TASK039_V4_H4_MODE_COUNT
        mpi_size = TASK039_V4_H4_MPI_SIZE
    else:
        raise InputError(f"unknown Task39 profile {profile!r}")
    source = _validate_source_sha(source_sha)
    inventory = task039_dynamic_external_mode_inventory(payload)
    return {
        "schema": schema,
        "scope": scope,
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
        "mode_count": mode_count,
        "mpi_size": mpi_size,
        "external_keys": {
            "count": len(inventory["keys"]),
            "sha256": _sha256_json(inventory["keys"]),
        },
    }


def write_v4_h4_mode_identity(
    specification: RunSpecification,
    source_sha: str,
    target: str | Path,
    *,
    profile: str = "v4-h4",
) -> tuple[dict[str, Any], str]:
    """Write the shared identity JSON and return it with its file SHA256."""

    identity = build_v4_h4_mode_identity(specification, source_sha, profile=profile)
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


def build_v5_h5_mode_identity(
    specification: RunSpecification,
    source_sha: str,
) -> dict[str, Any]:
    return build_v4_h4_mode_identity(specification, source_sha, profile="v5-h5")


def write_v5_h5_mode_identity(
    specification: RunSpecification,
    source_sha: str,
    target: str | Path,
) -> tuple[dict[str, Any], str]:
    return write_v4_h4_mode_identity(specification, source_sha, target, profile="v5-h5")


def _validate_shared_h4_mode_identity(
    identity: Mapping[str, Any],
    payload: Mapping[str, Any],
    *,
    profile: str = "v4-h4",
) -> None:
    """Check the method-independent packet authority against h4 input facts."""

    inventory = task039_dynamic_external_mode_inventory(payload)
    mesh = identity.get("mesh")
    external = identity.get("external_keys")
    provenance = payload.get("provenance")
    physical_sha = (
        provenance.get("physical_model_sha256")
        if isinstance(provenance, Mapping)
        else None
    )
    if profile == "v5-h5":
        expected_scope, expected_mesh, expected_mpi = (
            TASK039_V5_H5_MODE_SCOPE,
            5.0,
            TASK039_V5_H5_MPI_SIZE,
        )
    elif profile == "v4-h4":
        expected_scope, expected_mesh, expected_mpi = (
            TASK039_V4_H4_MODE_SCOPE,
            4.0,
            TASK039_V4_H4_MPI_SIZE,
        )
    else:
        raise InputError(f"unknown Task39 profile {profile!r}")
    if identity.get("scope") != expected_scope:
        raise InputError("Task39 packet identity scope does not match profile")
    if identity.get("method_independent") is not True:
        raise InputError("V4 h4 packet identity must be method-independent")
    if identity.get("physical_sha256") != physical_sha:
        raise InputError("V4 h4 packet physical identity does not match input")
    if not isinstance(mesh, Mapping) or mesh.get("target_nm") != expected_mesh:
        raise InputError("Task39 packet mesh identity does not match profile")
    if identity.get("mode_count") != TASK039_V4_H4_MODE_COUNT:
        raise InputError("Task39 packet identity requires M=480")
    if identity.get("mpi_size") != expected_mpi:
        raise InputError("Task39 packet identity requires MPI8")
    if not isinstance(external, Mapping) or (
        external.get("count") != len(inventory["keys"])
        or external.get("sha256") != _sha256_json(inventory["keys"])
    ):
        raise InputError("V4 h4 packet external-key identity does not match input")


def _phase_argv(
    specification: RunSpecification,
    output_directory: str | Path,
    source_sha: str,
    phase: str,
    *,
    identity_json: str | Path,
    packet_directory: str | Path | None = None,
    profile: str = "v4-h4",
) -> list[str]:
    if profile == "v5-h5":
        payload = validate_v5_h5_specification(specification)
    elif profile == "v4-h4":
        payload = validate_v4_h4_specification(specification)
    else:
        raise InputError(f"unknown Task39 profile {profile!r}")
    output = Path(output_directory).resolve() / "numerical_output" / "run_summary.json"
    if phase != "mode-prep":
        raise InputError("V4 phase argv is only used by the mode-prep worker")
    if packet_directory is None:
        raise InputError("mode-prep requires a packet directory")
    argv = _append_source_attestation(_argv_for_payload(payload, output), source_sha)
    argv.extend(
        [
            "--selected-mode-packet-producer-dir",
            str(Path(packet_directory).resolve()),
            "--selected-mode-packet-identity-json",
            str(Path(identity_json).resolve()),
            "--retained-subspace-dual-rotation",
        ]
    )
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
    profile: str = "v4-h4",
) -> ExecutionPlan:
    """Build the separate MPI8 worker command without starting it."""

    if profile == "v5-h5":
        validate_v5_h5_specification(specification)
        _validate_v5_h5_phase_method(specification, phase)
        profile_mpi_size = TASK039_V5_H5_MPI_SIZE
        profile_mode_count = TASK039_V5_H5_MODE_COUNT
        profile_adapter = TASK039_V5_H5_ADAPTER_IDENTITY
    elif profile == "v4-h4":
        validate_v4_h4_specification(specification)
        _validate_v4_h4_phase_method(specification, phase)
        profile_mpi_size = TASK039_V4_H4_MPI_SIZE
        profile_mode_count = TASK039_V4_H4_MODE_COUNT
        profile_adapter = (
            TASK039_V4_H4_ITERATIVE_ADAPTER_IDENTITY
            if phase == "iterative-consumer"
            else TASK039_V4_H4_ADAPTER_IDENTITY
        )
    else:
        raise InputError(f"unknown Task39 profile {profile!r}")
    if phase == "mode-prep" and packet_directory is None:
        raise InputError("mode-prep requires a packet directory")
    if phase in {"direct-consumer", "iterative-consumer"} and (
        manifest is None or manifest_sha256 is None
    ):
        raise InputError(f"{phase} requires manifest and manifest SHA256")
    if not Path(identity_json).is_file():
        raise InputError(f"V4 h4 mode identity is missing: {identity_json}")
    if phase in {"direct-consumer", "iterative-consumer"}:
        validate_v4_h4_packet_manifest(manifest, manifest_sha256)
    source = _validate_source_sha(source_sha)
    run_path = Path(run_directory).resolve()
    executable = Path(os.path.abspath(python_executable or sys.executable))
    mpiexec = mpiexec_command or shutil.which("mpiexec") or "mpiexec"
    worker_argv = [
        str(mpiexec),
        "-n",
        str(profile_mpi_size),
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
    if profile != "v4-h4":
        worker_argv.extend(["--profile", profile])
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
        method=(
            "hybrid_iterative" if phase == "iterative-consumer" else "hybrid_direct"
        ),
        mpi_size=profile_mpi_size,
        requested_modes=profile_mode_count,
        physical_model_sha256=specification.physical_model_sha256,
        input_sha256=specification.input_sha256,
        source_sha=source,
        adapter_identity=profile_adapter,
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
    profile: str = "v4-h4",
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
    if profile == "v5-h5":
        profile_adapter = TASK039_V5_H5_ADAPTER_IDENTITY
    else:
        profile_adapter = (
            TASK039_V4_H4_ITERATIVE_ADAPTER_IDENTITY
            if phase == "iterative-consumer"
            else TASK039_V4_H4_ADAPTER_IDENTITY
        )
    manifest_value, resolved_sha = _write_bootstrap(
        specification,
        run_path,
        source_sha=_validate_source_sha(source_sha),
        adapter_identity=profile_adapter,
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
        profile=profile,
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


def _run_v4_h4_iterative_consumer(
    payload: Mapping[str, Any],
    output_directory: str | Path,
    source_sha: str,
    *,
    identity_json: str | Path,
    manifest: str | Path,
    manifest_sha256: str,
) -> Mapping[str, Any]:
    """Run the V4 h4 packet consumer through the reviewed Candidate-D chain."""

    identity = json.loads(Path(identity_json).read_text(encoding="utf-8"))
    if not isinstance(identity, Mapping):
        raise InputError("V4 h4 packet identity must be a JSON object")
    _validate_shared_h4_mode_identity(identity, payload)
    actual_manifest_sha = validate_v4_h4_packet_manifest(manifest, manifest_sha256)
    identity_file_sha = hashlib.sha256(Path(identity_json).read_bytes()).hexdigest()
    identity_sha = _sha256_json(identity)

    from mpi4py import MPI

    comm = MPI.COMM_WORLD
    from benchmarks.run_task037b_hybrid_iterative import build_frozen_m10_setup
    from benchmarks.task039_v3_7_orchestration import (
        run_task039_v3_7_diagnostic,
        run_v3_7_recovery_runner,
    )
    from benchmarks.task039_v3_side_oracle import (
        TASK039_V4_H4_CASE_QUALIFICATION_SCOPE,
    )
    from src.runners.task039_hybrid_iterative import (
        make_task039_hybrid_iterative_profile,
    )

    profile = make_task039_hybrid_iterative_profile(
        TASK039_V4_H4_MODE_COUNT,
        TASK039_V4_H4_MPI_SIZE,
        mesh_target_nm=4.0,
    )
    qep_release_holder: dict[str, Any] = {}

    def setup_builder(comm, **kwargs):
        setup = build_frozen_m10_setup(
            comm,
            selected_mode_packet_manifest=Path(manifest),
            selected_mode_packet_identity=identity,
            selected_mode_packet_manifest_sha256=actual_manifest_sha,
            **kwargs,
        )
        qep_release_holder.update(dict(setup.qep_release))
        return setup

    inventory = task039_dynamic_external_mode_inventory(payload)
    producer_metadata = {
        "producer_source_sha": identity.get("source_sha"),
        "packet_producer_source_sha": identity.get("source_sha"),
        "consumer_source_sha": source_sha,
        "consumer_model_id": TASK039_V4_H4_HYBRID_ITERATIVE_MODEL_ID,
        "model_id": TASK039_V4_H4_HYBRID_ITERATIVE_MODEL_ID,
        "requested_modes": TASK039_V4_H4_MODE_COUNT,
        "mpi_size": TASK039_V4_H4_MPI_SIZE,
        "qualification_scope": TASK039_V4_H4_CASE_QUALIFICATION_SCOPE,
        "qualification_method": TASK039_V4_H4_QUALIFICATION_METHOD,
        "external_keys_exact": len(inventory["keys"])
        == len({json.dumps(key, sort_keys=True) for key in inventory["keys"]}),
        "selected_mode_packet": {
            "manifest": str(Path(manifest).resolve()),
            "manifest_sha256": actual_manifest_sha,
            "identity_json": str(Path(identity_json).resolve()),
            "identity_sha256": identity_sha,
            "identity_file_sha256": identity_file_sha,
            "consumer_kind": "iterative",
        },
        "_hybrid_direct_authority_run_directory": (
            "results/task039_v4_h4_hybrid_direct_formal_mpi8_icntl14_1515f095"
        ),
        "_full3d_authority_run_directory": None,
        "direct_reference_payload_loaded": False,
    }
    run_directory = Path(output_directory).resolve()
    result = run_task039_v3_7_diagnostic(
        payload,
        run_directory,
        source_sha=source_sha,
        setup_builder=setup_builder,
        profile_override=profile,
        producer_metadata=producer_metadata,
        recovery_runner=run_v3_7_recovery_runner,
        candidate_d_qualified=True,
        qualification_scope=TASK039_V4_H4_CASE_QUALIFICATION_SCOPE,
        qualification_method=TASK039_V4_H4_QUALIFICATION_METHOD,
        qualification_target=TASK039_V4_H4_QUALIFICATION_TARGET,
        comm=comm,
        record_path=run_directory
        / "numerical_output"
        / "v4_h4_iterative_consumer.json",
    )
    qep_release = dict(qep_release_holder)
    measured_qep_calls = qep_release.get("qep_calls")
    consumer_qep_required = qep_release.get("consumer_qep_required")
    measured_manifest_sha = qep_release.get("packet_manifest_sha256")
    measured_identity_sha = qep_release.get("packet_identity_sha256")
    packet_gate = _v4_h4_packet_consumer_gate(
        qep_release,
        manifest_sha256=actual_manifest_sha,
        identity_sha256=identity_sha,
    )
    candidate = result.get("candidate_d", {})
    recovery = candidate.get("recovery", {})
    integrated = (
        recovery.get("integrated_checker", {}) if isinstance(recovery, Mapping) else {}
    )
    result.update(
        {
            "phase": "iterative-consumer",
            "method": TASK039_V4_H4_QUALIFICATION_METHOD,
            "selected_mode_packet_consumer": {
                **producer_metadata["selected_mode_packet"],
                "qep_calls": measured_qep_calls,
                "consumer_qep_required": consumer_qep_required,
                "manifest_sha256": measured_manifest_sha,
                "identity_sha256": measured_identity_sha,
                "packet_read_seconds_max_rank": qep_release.get(
                    "packet_read_seconds_max_rank"
                ),
                "packet_hydrate_seconds_max_rank": qep_release.get(
                    "packet_hydrate_seconds_max_rank"
                ),
                "packet_mmap_released": qep_release.get("packet_mmap_released"),
                "packet_references_released": qep_release.get(
                    "packet_references_released"
                ),
            },
            "integrated_checker": integrated,
            "passed": bool(
                candidate.get("pass") is True
                and integrated.get("pass") is True
                and packet_gate
            ),
            "packet_consumer_gate": packet_gate,
        }
    )
    record_path = run_directory / "numerical_output" / "v4_h4_iterative_consumer.json"
    if comm.rank == 0:
        record_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
    comm.barrier()
    return result


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
    profile: str = "v4-h4",
) -> Mapping[str, Any]:
    """Execute one already-planned phase inside the MPI worker."""

    payload = json.loads(Path(resolved_config).read_text(encoding="utf-8"))
    specification = load_and_resolve(payload["provenance"]["source_path"])
    if profile == "v5-h5":
        validate_v5_h5_specification(specification)
        _validate_v5_h5_phase_method(specification, phase)
        identity = json.loads(Path(identity_json).read_text(encoding="utf-8"))
        if not isinstance(identity, Mapping):
            raise InputError("V5-S h5 mode identity must be a JSON object")
        _validate_shared_h4_mode_identity(identity, payload, profile="v5-h5")
    elif profile == "v4-h4":
        validate_v4_h4_specification(specification)
        _validate_v4_h4_phase_method(specification, phase)
    else:
        raise InputError(f"unknown Task39 profile {profile!r}")
    if phase in {"direct-consumer", "iterative-consumer"}:
        if manifest is None or manifest_sha256 is None:
            raise InputError(f"{phase} requires manifest and manifest SHA256")
        validate_v4_h4_packet_manifest(manifest, manifest_sha256)
    if phase == "mode-prep":
        from benchmarks.run_task032_phase6_augmented import main as run_task032_main

        argv = _phase_argv(
            specification,
            output_directory,
            source_sha,
            phase,
            identity_json=identity_json,
            packet_directory=packet_directory,
            profile=profile,
        )
        return run_task032_main(
            argv,
            config_override=simulation_config_3d_from_normalized(payload),
            use_case080_reference=False,
            canonical_export_prefix=(
                "task039_v5_h5_mode_prep"
                if profile == "v5-h5"
                else "task039_v4_mode_prep"
            ),
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
    if phase == "iterative-consumer":
        if profile != "v4-h4":
            raise InputError("V5-S h5 does not support iterative consumption")
        return _run_v4_h4_iterative_consumer(
            payload,
            output_directory,
            source_sha,
            identity_json=identity_json,
            manifest=manifest,
            manifest_sha256=manifest_sha256,
        )
    raise InputError(f"unknown V4 h4 phase {phase!r}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--phase",
        choices=("mode-prep", "direct-consumer", "iterative-consumer"),
        required=True,
    )
    parser.add_argument("--resolved-config", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--identity-json", type=Path, required=True)
    parser.add_argument("--packet-directory", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--manifest-sha256")
    parser.add_argument("--profile", choices=("v4-h4", "v5-h5"), default="v4-h4")
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
            profile=args.profile,
        )
        failed = not isinstance(result, Mapping) or result.get("passed") is False
    except Exception as exc:
        failed = True
        if MPI.COMM_WORLD.rank == 0:
            print(f"Task039 worker failed: {type(exc).__name__}: {exc}", flush=True)
    return 4 if MPI.COMM_WORLD.allreduce(failed, op=MPI.LOR) else 0


__all__ = [
    "TASK039_V4_H4_HYBRID_DIRECT_INPUT",
    "TASK039_V4_H4_HYBRID_ITERATIVE_INPUT",
    "TASK039_V4_H4_HYBRID_DIRECT_MODEL_ID",
    "TASK039_V4_H4_HYBRID_ITERATIVE_MODEL_ID",
    "TASK039_V4_H4_MODE_SCOPE",
    "TASK039_V4_H4_QUALIFICATION_METHOD",
    "TASK039_V4_H4_QUALIFICATION_TARGET",
    "TASK039_V5_H5_HYBRID_DIRECT_INPUT",
    "TASK039_V5_H5_HYBRID_DIRECT_MODEL_ID",
    "TASK039_V5_H5_MODE_SCOPE",
    "build_v4_h4_mode_identity",
    "build_v4_h4_phase_plan",
    "build_v5_h5_mode_identity",
    "launch_v4_h4_phase",
    "main",
    "run_v4_h4_worker",
    "validate_v4_h4_packet_manifest",
    "validate_v4_h4_specification",
    "validate_v5_h5_specification",
    "write_v4_h4_mode_identity",
    "write_v5_h5_mode_identity",
]


if __name__ == "__main__":
    raise SystemExit(main())
