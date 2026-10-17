"""Strict ABI qualification for frozen Task40 and Task41 candidate profiles."""

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
        raise RuntimeError(f"approved {label} escapes the execution root")
    return candidate


def qualified_task40_v10_abi(
    *,
    profile_identity: str,
    v30_contract_path: str | Path | None = None,
    v30_contract_sha256: str | None = None,
    v31_contract_path: str | Path | None = None,
    v31_contract_sha256: str | None = None,
) -> dict[str, object]:
    """Validate the qualified Task40 or Task41 runtime ABI receipt."""
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
    from src.geometry.task41_phi90_profile import (
        TASK41_B0_PRECONDITIONER,
        TASK41_G13_A2_PRECONDITIONER,
    )

    strict_v30 = os.environ.get("TASK40_V30_STRICT_EXECUTION") == "1"
    strict_v31 = os.environ.get("TASK40_V31_STRICT_EXECUTION") == "1"
    strict_task41 = os.environ.get("TASK41_P0_STRICT_EXECUTION") == "1"
    if strict_v30 and strict_v31:
        raise RuntimeError("Task40 V30 and V31 strict ABI contracts cannot be combined")
    if strict_task41 and (strict_v30 or strict_v31):
        raise RuntimeError(
            "Task41 P0 and Task40 V30/V31 strict ABI contracts cannot be combined"
        )

    task40_profiles = (
        TASK40_V10_P4_CONTROL_PROFILE,
        TASK40_V10_P6_REFERENCE_PROFILE,
        *TASK40_V11_P6_PROFILES,
        *TASK40_V15_P6_PROFILES,
        *TASK40_V16_P6_PROFILES,
        *TASK40_V17_P6_PROFILES,
        *TASK40_V18_P6_PROFILES,
        *TASK40_V20_P6_PROFILES,
    )
    task41_case_by_profile = {
        TASK41_G13_A2_PRECONDITIONER: "A2",
        TASK41_B0_PRECONDITIONER: "B0",
    }
    if strict_task41:
        if profile_identity not in task41_case_by_profile:
            raise RuntimeError(
                "Task41 P0 ABI gate accepts only its exact A2 or B0 profile"
            )
    elif profile_identity in task41_case_by_profile:
        raise RuntimeError("Task41 P0 ABI gate requires the strict P0 execution contract")
    elif profile_identity not in task40_profiles:
        raise RuntimeError(
            "Task40 V10/V11 ABI gate accepts only an exact reviewed p4/p6 profile"
        )

    root = Path(__file__).resolve().parents[2]
    if strict_task41:
        if any(
            value is not None
            for value in (
                v30_contract_path,
                v30_contract_sha256,
                v31_contract_path,
                v31_contract_sha256,
            )
        ):
            raise RuntimeError("Task41 P0 ABI gate cannot use a Task40 V30/V31 contract")
        contract_path_value = os.environ.get("TASK41_P0_CONTRACT_PATH")
        contract_sha256 = os.environ.get("TASK41_P0_CONTRACT_SHA256")
        if not contract_path_value or not contract_sha256:
            raise RuntimeError("Task41 P0 ABI gate requires its bound execution contract")
        from src.runners.task41_p0_contract import (
            TASK41_A2_RUN_ID,
            TASK41_B0_RUN_ID,
            require_task41_p0_contract,
        )

        task41_case_id = task41_case_by_profile[profile_identity]
        expected_run_id = (
            TASK41_A2_RUN_ID if task41_case_id == "A2" else TASK41_B0_RUN_ID
        )
        contract, checked_contract_sha256 = require_task41_p0_contract(
            contract_path_value,
            expected_sha256=contract_sha256,
            current_root=root,
            check_current_source=True,
            require_clean_source=True,
            case_id=task41_case_id,
        )
        if (
            checked_contract_sha256 != contract_sha256
            or contract["case"].get("run_id") != expected_run_id
        ):
            raise RuntimeError(
                f"Task41 P0 ABI contract differs from the exact {task41_case_id} service binding"
            )
        execution = contract["runtime"]
        runtime_profile = str(execution["profile"])
        if runtime_profile != "native_linux":
            raise RuntimeError(
                "Task41 P0 ABI gate requires the contract-bound native_linux runtime"
            )
        prefix = _rooted_contract_path(
            root, execution["runtime_prefix"], "Task41 runtime prefix"
        )
        receipt_path = _rooted_contract_path(
            root, execution["abi_receipt_path"], "Task41 ABI receipt"
        )
        expected_receipt_sha256 = str(execution["abi_receipt_sha256"])
    elif strict_v30:
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
    elif strict_v31:
        if profile_identity != TASK40_V20_P6_TARGET_ORIGINAL_NY8_PROFILE:
            raise RuntimeError(
                "Task40 V31 native ABI receipt is restricted to the approved target Ny8 profile"
            )
        if v31_contract_path is None or not v31_contract_sha256:
            raise RuntimeError("Task40 V31 ABI gate requires its approved contract binding")
        from src.runners.task40_v30_contract import V30_ABI_RECEIPT_SHA256
        from src.runners.task40_v31_contract import (
            require_v31_execution_contract,
            v31_launcher_values,
        )

        contract_path = Path(v31_contract_path)
        contract_path = (
            contract_path if contract_path.is_absolute() else root / contract_path
        ).resolve()
        configured_contract = Path(
            os.environ.get("TASK40_V31_CONTRACT_PATH", "")
        ).resolve()
        configured_contract_sha256 = os.environ.get("TASK40_V31_CONTRACT_SHA256")
        if (
            contract_path != configured_contract
            or v31_contract_sha256 != configured_contract_sha256
        ):
            raise RuntimeError("Task40 V31 ABI gate contract differs from the worker binding")
        v31_contract, checked_contract_sha256 = require_v31_execution_contract(
            contract_path,
            expected_sha256=v31_contract_sha256,
            current_root=root,
        )
        execution = v31_contract["execution"]
        launcher_binding = v31_launcher_values(
            contract_path,
            expected_sha256=v31_contract_sha256,
            current_root=root,
        )
        runtime_profile = "native_linux"
        prefix = Path(launcher_binding[1]).resolve()
        receipt_path = Path(launcher_binding[2]).resolve()
        expected_receipt_sha256 = V30_ABI_RECEIPT_SHA256
        if checked_contract_sha256 != configured_contract_sha256:
            raise RuntimeError("Task40 V31 ABI gate contract hash changed during validation")
    else:
        if any(
            value is not None
            for value in (
                v30_contract_path,
                v30_contract_sha256,
                v31_contract_path,
                v31_contract_sha256,
            )
        ):
            raise RuntimeError("Task40 ABI contract binding requires its matching strict mode")
        prefix = (root / _RUNTIME_PREFIX).resolve()
        receipt_path = (root / _ABI_RECEIPT).resolve()
        expected_receipt_sha256 = _ABI_RECEIPT_SHA256
        from benchmarks.task40_runtime_profile import LOCAL_WSL2_PROFILE

        runtime_profile = LOCAL_WSL2_PROFILE

    abi_family = "Task41 P0" if strict_task41 else "Task40 V10"
    strict_native = (strict_v30 or strict_v31 or strict_task41) and (
        runtime_profile == "native_linux"
    )

    try:
        receipt_bytes = receipt_path.read_bytes()
    except OSError as exc:
        receipt_label = (
            "Task41 P0"
            if strict_task41
            else "Task40 V31 approved"
            if strict_v31
            else "Task40 V30 approved"
            if strict_v30
            else "Task40 V10 qualified"
        )
        raise RuntimeError(f"{receipt_label} ABI receipt is unavailable") from exc
    receipt_sha256 = hashlib.sha256(receipt_bytes).hexdigest()
    if receipt_sha256 != expected_receipt_sha256:
        receipt_label = (
            "Task41 P0"
            if strict_task41
            else "Task40 V31 approved"
            if strict_v31
            else "Task40 V30 approved"
            if strict_v30
            else "Task40 V10 qualified"
        )
        raise RuntimeError(f"{receipt_label} ABI receipt hash differs from its binding")

    configured_receipt = os.environ.get("_MYFENICS_CLOUD_ABI_MANIFEST")
    configured_sha256 = os.environ.get("_MYFENICS_CLOUD_ABI_MANIFEST_SHA256")
    if (
        (
            os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") != "1"
            if not strict_native
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
        raise RuntimeError(f"{abi_family} activation or ABI receipt binding differs from the approved profile")

    try:
        receipt = json.loads(receipt_bytes)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{abi_family} qualified ABI receipt is not valid JSON") from exc
    if (
        receipt.get("status") != "IMPORT_SCALAR_MPI_API_PASS_NO_FE_ACTION"
        or receipt.get("runtime_profile") != runtime_profile
        or receipt.get("FE_action") != "NOT_RUN"
        or receipt.get("matrix_creation_calls") != 0
        or receipt.get("factor_calls") != 0
        or receipt.get("PDE_calls") != 0
        or receipt.get("old_ABI_inherited") is not False
    ):
        raise RuntimeError(f"{abi_family} ABI receipt does not describe the approved imports-only qualification")

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
        raise RuntimeError("runtime profile constants changed unexpectedly")
    if (
        Path(sys.executable).resolve() != (prefix / "bin/python").resolve()
        or Path(sys.prefix).resolve() != prefix
    ):
        raise RuntimeError(f"{abi_family} Python executable/prefix differs from the qualified runtime")

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
        raise RuntimeError(f"{abi_family} live PETSc/MPI/scalar identity differs from the qualified receipt")

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
            raise RuntimeError(f"{abi_family} module path/version differs from qualified receipt: {name}")
        module_facts[name] = {"path": str(module_path), "version": version}

    mpi_extension = Path(MPI.__file__).resolve()
    expected_mpi_extension = Path(receipt["MPI"]["extension_file"]).resolve()
    if mpi_extension != expected_mpi_extension or not mpi_extension.is_relative_to(prefix):
        raise RuntimeError(f"{abi_family} mpi4py extension path differs from qualified receipt")
    threads = {name: os.environ.get(name) for name in _THREAD_VARIABLES}
    if set(threads.values()) != {"1"}:
        raise RuntimeError(f"{abi_family} qualified ABI requires all thread limits to equal one")

    return {
        "qualification": (
            "task41_p0_contract_receipt_bound"
            if strict_task41
            else "task40_v10_exact_profile_receipt_bound"
        ),
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
