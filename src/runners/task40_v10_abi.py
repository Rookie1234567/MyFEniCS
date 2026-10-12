"""Strict ABI qualification for frozen Task40 V10/V11 p6 candidate profiles."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
from pathlib import Path
import sys

_RUNTIME_PREFIX = Path(
    "benchmarks/artifacts/task40extra_0p7nm_engineering/"
    "local_w0_wsl/runtime_prefix"
)
_ABI_RECEIPT = Path(
    "benchmarks/artifacts/task40extra_0p7nm_engineering/"
    "local_w0_wsl/continuation_attempt4/abi_receipt.json"
)
_ABI_RECEIPT_SHA256 = "ac3a1120d8061fc91c818150177977e619de2fccb27fed1262cea45d90268426"
_THREAD_VARIABLES = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
)


def _rooted_contract_path(root: Path, value: object, label: str) -> Path:
    supplied = Path(str(value))
    candidate = (supplied if supplied.is_absolute() else root / supplied).resolve()
    if not candidate.is_relative_to(root):
        raise RuntimeError(f"Task40 V30 {label} escapes the approved execution root")
    return candidate


def qualified_task40_v10_abi(
    *,
    profile_identity: str,
    v30_contract_path: str | Path | None = None,
    v30_contract_sha256: str | None = None,
) -> dict[str, object]:
    """Validate the legacy WSL receipt or the strictly authorized V30 receipt."""
    from src.io.physical_intermediate_profile import (
        TASK40_V10_P4_CONTROL_PROFILE,
        TASK40_V10_P6_REFERENCE_PROFILE,
        TASK40_V11_P6_PROFILES,
        TASK40_V15_P6_PROFILES,
        TASK40_V16_P6_PROFILES,
        TASK40_V17_P6_PROFILES,
        TASK40_V18_P6_PROFILES,
        TASK40_V20_P6_PROFILES,
        TASK40_V20_P6_TARGET_ORIGINAL_NY8_PROFILE,
    )

    if profile_identity not in (
        TASK40_V10_P4_CONTROL_PROFILE,
        TASK40_V10_P6_REFERENCE_PROFILE,
        *TASK40_V11_P6_PROFILES,
        *TASK40_V15_P6_PROFILES,
        *TASK40_V16_P6_PROFILES,
        *TASK40_V17_P6_PROFILES,
        *TASK40_V18_P6_PROFILES,
        *TASK40_V20_P6_PROFILES,
    ):
        raise RuntimeError(
            "Task40 V10/V11 ABI gate accepts only an exact reviewed p4/p6 profile"
        )

    root = Path(__file__).resolve().parents[2]
    strict_v30 = os.environ.get("TASK40_V30_STRICT_EXECUTION") == "1"
    if strict_v30:
        if profile_identity != TASK40_V20_P6_TARGET_ORIGINAL_NY8_PROFILE:
            raise RuntimeError(
                "Task40 V30 native ABI receipt is restricted to the approved target Ny8 profile"
            )
        if v30_contract_path is None or not v30_contract_sha256:
            raise RuntimeError("Task40 V30 ABI gate requires its approved contract binding")
        from src.runners.task40_v30_contract import require_authorized_contract

        contract_path = Path(v30_contract_path)
        contract_path = (
            contract_path if contract_path.is_absolute() else root / contract_path
        ).resolve()
        configured_contract = Path(
            os.environ.get("TASK40_V30_CONTRACT_PATH", "")
        ).resolve()
        configured_contract_sha256 = os.environ.get("TASK40_V30_CONTRACT_SHA256")
        if (
            contract_path != configured_contract
            or v30_contract_sha256 != configured_contract_sha256
        ):
            raise RuntimeError("Task40 V30 ABI gate contract differs from the worker binding")
        v30_contract, checked_contract_sha256 = require_authorized_contract(
            contract_path,
            expected_sha256=v30_contract_sha256,
            current_root=root,
        )
        execution = v30_contract["execution"]
        runtime_profile = str(execution["host_identity"]["runtime_profile"])
        if runtime_profile != "native_linux":
            raise RuntimeError("Task40 V30 ABI gate requires the approved native_linux profile")
        prefix = _rooted_contract_path(root, execution["runtime_prefix"], "runtime prefix")
        receipt_path = _rooted_contract_path(root, execution["abi_receipt_path"], "ABI receipt")
        expected_receipt_sha256 = str(execution["abi_receipt_sha256"])
        if checked_contract_sha256 != configured_contract_sha256:
            raise RuntimeError("Task40 V30 ABI gate contract hash changed during validation")
    else:
        if v30_contract_path is not None or v30_contract_sha256 is not None:
            raise RuntimeError("Task40 V30 ABI binding requires strict V30 execution mode")
        prefix = (root / _RUNTIME_PREFIX).resolve()
        receipt_path = (root / _ABI_RECEIPT).resolve()
        expected_receipt_sha256 = _ABI_RECEIPT_SHA256
        from benchmarks.task40_runtime_profile import LOCAL_WSL2_PROFILE

        runtime_profile = LOCAL_WSL2_PROFILE

    try:
        receipt_bytes = receipt_path.read_bytes()
    except OSError as exc:
        receipt_label = "V30 approved" if strict_v30 else "V10 qualified"
        raise RuntimeError(f"Task40 {receipt_label} ABI receipt is unavailable") from exc
    receipt_sha256 = hashlib.sha256(receipt_bytes).hexdigest()
    if receipt_sha256 != expected_receipt_sha256:
        receipt_label = "V30 approved" if strict_v30 else "V10 qualified"
        raise RuntimeError(f"Task40 {receipt_label} ABI receipt hash differs from its binding")

    configured_receipt = os.environ.get("_MYFENICS_CLOUD_ABI_MANIFEST")
    configured_sha256 = os.environ.get("_MYFENICS_CLOUD_ABI_MANIFEST_SHA256")
    if (
        (
            os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") != "1"
            if not strict_v30
            else os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") is not None
        )
        or os.environ.get("_MYFENICS_CLOUD_QUALIFIED_ACTIVATION") != "1"
        or os.environ.get("_MYFENICS_CLOUD_RUNTIME_PROFILE") != runtime_profile
        or os.environ.get("_MYFENICS_CLOUD_QUALIFICATION_SCOPE")
        != "imports_only_C1_FE_JIT_NOT_RUN"
        or not configured_receipt
        or Path(configured_receipt).resolve() != receipt_path
        or configured_sha256 != receipt_sha256
    ):
        raise RuntimeError("Task40 activation or ABI receipt binding differs from the approved profile")

    try:
        receipt = json.loads(receipt_bytes)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Task40 V10 qualified ABI receipt is not valid JSON") from exc
    if (
        receipt.get("status") != "IMPORT_SCALAR_MPI_API_PASS_NO_FE_ACTION"
        or receipt.get("runtime_profile") != runtime_profile
        or receipt.get("FE_action") != "NOT_RUN"
        or receipt.get("matrix_creation_calls") != 0
        or receipt.get("factor_calls") != 0
        or receipt.get("PDE_calls") != 0
        or receipt.get("old_ABI_inherited") is not False
    ):
        raise RuntimeError("Task40 V10 ABI receipt does not describe the approved imports-only qualification")

    from benchmarks.task40_runtime_profile import (
        LOCAL_WSL2_PROFILE,
        NATIVE_LINUX_PROFILE,
        validate_runtime_receipt,
    )

    host_binding = validate_runtime_receipt(
        receipt, requested_profile=runtime_profile
    )
    if (
        LOCAL_WSL2_PROFILE != "local_wsl2_authorized"
        or NATIVE_LINUX_PROFILE != "native_linux"
    ):
        raise RuntimeError("Task40 runtime profile constants changed unexpectedly")
    if (
        Path(sys.executable).resolve() != (prefix / "bin/python").resolve()
        or Path(sys.prefix).resolve() != prefix
    ):
        raise RuntimeError("Task40 V10 Python executable/prefix differs from the qualified runtime")

    import numpy as np
    from mpi4py import MPI
    from petsc4py import PETSc
    import dolfinx

    if (
        np.dtype(PETSc.ScalarType).name != "complex128"
        or np.dtype(PETSc.IntType).name != "int32"
        or np.dtype(PETSc.ScalarType).name != receipt["PETSc"]["scalar_dtype"]
        or np.dtype(PETSc.IntType).name != receipt["PETSc"]["int_dtype"]
        or list(PETSc.Sys.getVersion()) != receipt["PETSc"]["version"]
        or MPI.COMM_WORLD.Get_size() != 1
        or MPI.COMM_WORLD.Get_rank() != 0
        or MPI.Get_library_version() != receipt["MPI"]["library_version"]
        or np.dtype(dolfinx.default_scalar_type).name
        != receipt["dolfinx_default_scalar_dtype"]
        or os.environ.get("UCX_TLS") != receipt["process_local_UCX_TLS"]
    ):
        raise RuntimeError("Task40 V10 live PETSc/MPI/scalar identity differs from the qualified receipt")

    module_facts: dict[str, dict[str, object]] = {}
    for name, expected in receipt["modules"].items():
        module = importlib.import_module(name)
        module_path = Path(module.__file__).resolve()
        expected_path = Path(expected["file"]).resolve()
        version = getattr(module, "__version__", None)
        if (
            module_path != expected_path
            or not module_path.is_relative_to(prefix)
            or (expected.get("version") is not None and version != expected["version"])
        ):
            raise RuntimeError(f"Task40 V10 module path/version differs from qualified receipt: {name}")
        module_facts[name] = {"path": str(module_path), "version": version}

    mpi_extension = Path(MPI.__file__).resolve()
    expected_mpi_extension = Path(receipt["MPI"]["extension_file"]).resolve()
    if mpi_extension != expected_mpi_extension or not mpi_extension.is_relative_to(prefix):
        raise RuntimeError("Task40 V10 mpi4py extension path differs from qualified receipt")
    threads = {name: os.environ.get(name) for name in _THREAD_VARIABLES}
    if set(threads.values()) != {"1"}:
        raise RuntimeError("Task40 V10 qualified ABI requires all thread limits to equal one")

    return {
        "qualification": "task40_v10_exact_profile_receipt_bound",
        "profile_identity": profile_identity,
        "runtime_profile": runtime_profile,
        "runtime_host_binding": host_binding,
        "python_executable": str(Path(sys.executable).resolve()),
        "runtime_prefix": str(prefix),
        "receipt_path": str(receipt_path),
        "receipt_sha256": receipt_sha256,
        "receipt_source_sha256": receipt.get("source_sha256"),
        "scalar": np.dtype(PETSc.ScalarType).name,
        "integer": np.dtype(PETSc.IntType).name,
        "petsc_version": list(PETSc.Sys.getVersion()),
        "mpi_size": MPI.COMM_WORLD.Get_size(),
        "mpi_library_version": MPI.Get_library_version(),
        "mpi_extension": str(mpi_extension),
        "threads": threads,
        "modules": module_facts,
    }
