"""Task38 execution-plan identity and stable dry-run description."""

from __future__ import annotations

import hashlib
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .input_loader import InputError
from .resolved_config import resolved_config_bytes
from .run_specification import RunSpecification


WORKER_MODULE = "src.runners.task038_input_worker"
CONTRACT_PROBE_ADAPTER = "task038.contract_probe"
METHOD_ADAPTERS = {
    "2d_scattered": "task038.2d_scattered",
    "2d_port": "task038.2d_port",
    "full3d_direct": "task038.full3d_direct",
    "hybrid_direct": "task038.hybrid_direct",
    "hybrid_iterative": "task038.hybrid_iterative",
}
CONNECTED_METHODS = frozenset(
    {"2d_scattered", "2d_port", "full3d_direct", "hybrid_direct", "hybrid_iterative"}
)


@dataclass(frozen=True)
class ExecutionPlan:
    """Immutable private worker command and identity contract."""

    argv: tuple[str, ...]
    shell: bool
    executable: Path
    worker_module: str
    method: str
    mpi_size: int
    requested_modes: int | None
    physical_model_sha256: str
    input_sha256: str
    source_sha: str
    adapter_identity: str
    adapter_available: bool
    contract_probe: bool
    expected_output_directory: Path
    expected_resolved_config: Path
    expected_manifest: Path


def method_adapter_identity(method: str) -> str:
    try:
        return METHOD_ADAPTERS[method]
    except KeyError as exc:
        raise InputError(
            f"method.kind: no Task38 adapter identity for {method!r}"
        ) from exc


def method_adapter_available(method: str) -> bool:
    """Report availability of the adapters actually connected in Task38."""

    if method not in METHOD_ADAPTERS:
        raise InputError(f"method.kind: unsupported Task38 method {method!r}")
    return method in CONNECTED_METHODS


def build_execution_plan(
    specification: RunSpecification,
    run_directory: str | Path,
    *,
    source_sha: str,
    python_executable: str | Path | None = None,
    mpiexec_command: str | None = None,
    adapter_identity: str | None = None,
    contract_probe: bool = False,
) -> ExecutionPlan:
    """Build the private worker argv without shell interpolation or overrides."""

    run_directory = Path(run_directory).resolve()
    executable = Path(python_executable or sys.executable).resolve()
    method = str(specification.method["kind"])
    if contract_probe:
        if adapter_identity != CONTRACT_PROBE_ADAPTER:
            raise InputError(
                "contract probe requires the private contract-probe adapter"
            )
        adapter = CONTRACT_PROBE_ADAPTER
        available = True
    else:
        adapter = adapter_identity or method_adapter_identity(method)
        if adapter != method_adapter_identity(method):
            raise InputError("public method adapter identity cannot be overridden")
        available = method_adapter_available(method)

    mpi_size = int(specification.execution["mpi_size"])
    requested_modes = specification.method.get("requested_modes_per_direction")
    resolved_path = run_directory / "resolved_config.json"
    manifest_path = run_directory / "run_manifest.json"
    mpiexec = mpiexec_command or shutil.which("mpiexec") or "mpiexec"
    argv = [
        str(mpiexec),
        "-n",
        str(mpi_size),
        str(executable),
        "-m",
        WORKER_MODULE,
        "--resolved-config",
        str(resolved_path),
        "--manifest",
        str(manifest_path),
        "--expected-input-sha256",
        specification.input_sha256,
        "--expected-physical-model-sha256",
        specification.physical_model_sha256,
        "--expected-source-sha",
        source_sha,
        "--expected-mpi-size",
        str(mpi_size),
        "--expected-method",
        method,
        "--expected-adapter",
        adapter,
        "--expected-output-directory",
        str(run_directory),
        "--resolved-config-sha256",
        hashlib.sha256(resolved_config_bytes(specification)).hexdigest(),
    ]
    if contract_probe:
        argv.append("--contract-probe")
    return ExecutionPlan(
        argv=tuple(argv),
        shell=False,
        executable=executable,
        worker_module=WORKER_MODULE,
        method=method,
        mpi_size=mpi_size,
        requested_modes=requested_modes,
        physical_model_sha256=specification.physical_model_sha256,
        input_sha256=specification.input_sha256,
        source_sha=source_sha,
        adapter_identity=adapter,
        adapter_available=available,
        contract_probe=contract_probe,
        expected_output_directory=run_directory,
        expected_resolved_config=resolved_path,
        expected_manifest=manifest_path,
    )


def dry_run_payload(specification: RunSpecification) -> dict[str, Any]:
    """Return stable, non-mutating Task38 dry-run fields."""

    snapshot = specification.as_jsonable()
    derived = snapshot["derived"]
    internal = derived["internal"]
    incidence = snapshot["incidence"]
    phases = (
        {
            "x": derived.get("floquet_phase_x"),
            "y": derived.get("floquet_phase_y"),
        }
        if "floquet_phase_x" in derived
        else {"x": derived.get("floquet_phase"), "y": None}
    )
    return {
        "method": specification.method["kind"],
        "mpi_size": specification.execution["mpi_size"],
        "requested_modes_per_direction": specification.method.get(
            "requested_modes_per_direction"
        ),
        "physical_model_sha256": specification.physical_model_sha256,
        "theta_deg": internal.get("incident_theta_deg"),
        "grazing_angle_deg": incidence.get("grazing_angle_deg"),
        "tilt_from_downward_z_deg": incidence.get("tilt_from_downward_z_deg"),
        "azimuth_deg": incidence.get("azimuth_deg"),
        "wavevector": derived.get("wavevector"),
        "polarization": derived.get("polarization"),
        "floquet_phases": phases,
        "expected_output_directory": str(
            Path(specification.expected_output_parent).resolve()
        ),
        "resolved_method_adapter": {
            "identity": method_adapter_identity(specification.method["kind"]),
            "status": (
                "connected"
                if method_adapter_available(specification.method["kind"])
                else "unavailable"
            ),
        },
    }


__all__ = [
    "CONTRACT_PROBE_ADAPTER",
    "CONNECTED_METHODS",
    "ExecutionPlan",
    "METHOD_ADAPTERS",
    "WORKER_MODULE",
    "build_execution_plan",
    "dry_run_payload",
    "method_adapter_available",
    "method_adapter_identity",
]
