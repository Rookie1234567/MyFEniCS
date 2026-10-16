"""Fixed Task41 P0 source, input, runtime, resource, and deadline contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from typing import Any, Mapping

from src.runners.task40_v10_campaign import FixedCampaignWindow, _utc_ns
from src.runners.workflow_timebase import clock_sample

TASK41_P0_CONTRACT_SCHEMA = "task41.p0.execution_contract.v1"
TASK41_P0_WINDOW_SCHEMA = "task41.p0.execution_window.v1"
TASK41_P0_AUTH_SCHEMA = "task41.p0.closeout_checker_authorization.v1"
TASK41_BRANCH = "task41extra_phi90_p50x50_g17x20"
TASK41_MODEL_ID = "task41extra_phi90_p50x50_g17x20"
TASK41_RUN_ID = "task41extra_g13_p6_phi90_direct_a1"
TASK41_CONTROLLER_RELATIVE = Path(
    "benchmarks/artifacts/task41extra_phi90_p50x50_g17x20/p0_controller"
)
TASK41_WINDOW_RELATIVE = Path(
    "benchmarks/artifacts/task41extra_phi90_p50x50_g17x20/p0_controller/execution_window.json"
)
TASK41_INPUT_RELATIVE = Path(
    "input/task41extra_phi90_p50x50_g17x20/g13_p6_direct_a1.dat"
)
TASK41_TOTAL_SECONDS = 172_800.0
TASK41_NUMERICAL_SECONDS = 171_600.0
TASK41_CLOSEOUT_SECONDS = 1_200.0
TASK41_TASK_MEMORY_MAX_BYTES = 1_649_267_441_664
TASK41_HOST_RESERVE_BYTES = 68_719_476_736


class Task41ContractError(ValueError):
    """The fixed Task41 P0 execution contract is incomplete or inconsistent."""


def sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _utc_text_from_ns(value: int) -> str:
    seconds, nanoseconds = divmod(int(value), 1_000_000_000)
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(seconds)) + (
        f".{nanoseconds:09d}Z"
    )


def _write_json_no_replace(path: Path, payload: Mapping[str, Any]) -> bool:
    """Atomically create one JSON file without ever replacing an existing record."""
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            return False
        directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return True
    finally:
        temporary.unlink(missing_ok=True)


def _resolve(root: Path, raw: Any, label: str) -> Path:
    if not isinstance(raw, str) or not raw or "\n" in raw:
        raise Task41ContractError(f"{label} must be a nonempty path")
    path = Path(raw)
    return (path if path.is_absolute() else root / path).resolve()


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def contract_relative_path(source_sha: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise Task41ContractError("Task41 source SHA is invalid")
    return TASK41_CONTROLLER_RELATIVE / f"execution_contract_source_{source_sha}.json"


def require_task41_p0_contract(
    path: str | Path,
    *,
    expected_sha256: str | None = None,
    current_root: str | Path | None = None,
    require_clean_source: bool = False,
    check_current_source: bool = False,
) -> tuple[dict[str, Any], str]:
    root = Path(current_root or Path(__file__).resolve().parents[2]).resolve()
    contract_path = _resolve(root, str(path), "contract path")
    try:
        relative = contract_path.relative_to(root)
    except ValueError as exc:
        raise Task41ContractError("Task41 contract escaped the repository") from exc
    if relative.parent != TASK41_CONTROLLER_RELATIVE or not re.fullmatch(
        r"execution_contract_source_[0-9a-f]{40}\.json", relative.name
    ):
        raise Task41ContractError("Task41 contract is not in the registered P0 controller directory")
    raw = contract_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise Task41ContractError("Task41 contract SHA-256 differs from the launch binding")
    contract = json.loads(raw)
    if not isinstance(contract, dict) or contract.get("schema") != TASK41_P0_CONTRACT_SCHEMA:
        raise Task41ContractError("Task41 P0 execution contract schema is invalid")
    if contract.get("task_id") != TASK41_MODEL_ID or contract.get("branch") != TASK41_BRANCH:
        raise Task41ContractError("Task41 contract task or branch identity differs")
    source = contract.get("source")
    case = contract.get("case")
    runtime = contract.get("runtime")
    window = contract.get("window")
    resources = contract.get("resources")
    time_limits = contract.get("time")
    evidence = contract.get("evidence")
    if not all(
        isinstance(item, dict)
        for item in (source, case, runtime, window, resources, time_limits, evidence)
    ):
        raise Task41ContractError("Task41 contract sections must be JSON objects")
    if not re.fullmatch(r"[0-9a-f]{40}", str(source.get("sha", ""))):
        raise Task41ContractError("Task41 contract source SHA is invalid")
    if relative != contract_relative_path(str(source["sha"])):
        raise Task41ContractError("Task41 contract filename is not bound to its source SHA")
    if check_current_source:
        if _git(root, "rev-parse", "HEAD") != source["sha"]:
            raise Task41ContractError("Task41 source HEAD differs from the fixed contract")
        if _git(root, "branch", "--show-current") != TASK41_BRANCH:
            raise Task41ContractError("Task41 current branch differs from the fixed contract")
    if require_clean_source and _git(
        root, "status", "--porcelain", "--untracked-files=normal"
    ):
        raise Task41ContractError("Task41 formal execution requires a clean frozen source tree")

    input_path = _resolve(root, case.get("input_path"), "Task41 DAT path")
    if (
        input_path != (root / TASK41_INPUT_RELATIVE).resolve()
        or not input_path.is_file()
        or sha256_file(input_path) != case.get("input_sha256")
        or case.get("model_id") != TASK41_MODEL_ID
        or case.get("run_id") != TASK41_RUN_ID
        or not re.fullmatch(r"[0-9a-f]{64}", str(case.get("physical_model_sha256", "")))
        or not re.fullmatch(r"[0-9a-f]{64}", str(case.get("resolved_config_sha256", "")))
        or case.get("method") != "full3d_direct"
        or case.get("mpi_size") != 1
    ):
        raise Task41ContractError("Task41 contract does not bind the registered G13 direct input")

    for key in ("runtime_prefix", "abi_receipt_path", "jit_cache"):
        if not _resolve(root, runtime.get(key), f"runtime.{key}").exists():
            raise Task41ContractError(f"Task41 runtime.{key} does not exist")
    runtime_prefix = _resolve(root, runtime["runtime_prefix"], "runtime.runtime_prefix")
    if not (runtime_prefix / "bin" / "python").is_file() or not os.access(
        runtime_prefix / "bin" / "python", os.X_OK
    ):
        raise Task41ContractError("Task41 runtime prefix has no executable bin/python")
    abi_path = _resolve(root, runtime["abi_receipt_path"], "runtime.abi_receipt_path")
    if sha256_file(abi_path) != runtime.get("abi_receipt_sha256"):
        raise Task41ContractError("Task41 ABI receipt hash differs from the contract")
    if runtime.get("mpi_ranks") != 1 or runtime.get("math_threads") != 1:
        raise Task41ContractError("Task41 runtime must be MPI1 with one math thread")
    if runtime.get("profile") != "native_linux":
        raise Task41ContractError("formal Task41 P0 execution requires the registered native_linux runtime")
    window_path = _resolve(root, window.get("path"), "window.path")
    if window_path != (root / TASK41_WINDOW_RELATIVE).resolve():
        raise Task41ContractError("Task41 fixed window path is not registered")
    if not re.fullmatch(r"[0-9a-f]{64}", str(window.get("sha256", ""))):
        raise Task41ContractError("Task41 fixed window SHA-256 is invalid")
    if (
        resources.get("task_memory_max_bytes") != TASK41_TASK_MEMORY_MAX_BYTES
        or resources.get("host_reserve_bytes") != TASK41_HOST_RESERVE_BYTES
        or resources.get("memory_swap_max_bytes") != 0
    ):
        raise Task41ContractError("Task41 resource limits differ from the task ceiling")
    if (
        time_limits.get("total_seconds") != TASK41_TOTAL_SECONDS
        or time_limits.get("numerical_seconds") != TASK41_NUMERICAL_SECONDS
        or time_limits.get("closeout_seconds") != TASK41_CLOSEOUT_SECONDS
    ):
        raise Task41ContractError("Task41 contract time limits differ from the fixed P0 window")
    service_directory = _resolve(root, evidence.get("service_directory"), "evidence.service_directory")
    try:
        service_directory.relative_to(
            root / "benchmarks/artifacts/task41extra_phi90_p50x50_g17x20"
        )
    except ValueError as exc:
        raise Task41ContractError("Task41 service evidence escaped its artifact directory") from exc
    return contract, digest


def load_task41_p0_fixed_window(
    contract: Mapping[str, Any], *, current_root: str | Path | None = None,
    require_current_boot: bool = True,
) -> FixedCampaignWindow:
    root = Path(current_root or Path(__file__).resolve().parents[2]).resolve()
    window_info = contract["window"]
    path = _resolve(root, window_info["path"], "window.path")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != window_info["sha256"]:
        raise Task41ContractError("Task41 fixed execution window hash changed")
    payload = json.loads(raw)
    expected_fields = {
        "schema", "task_id", "source_sha", "t0_utc", "numerical_deadline_utc",
        "deadline_utc", "total_seconds", "numerical_seconds", "closeout_seconds",
        "anchor", "accounting_path",
    }
    if not isinstance(payload, dict) or set(payload) != expected_fields:
        raise Task41ContractError("Task41 fixed execution window has an open or incomplete schema")
    if (
        payload.get("schema") != TASK41_P0_WINDOW_SCHEMA
        or payload.get("task_id") != TASK41_MODEL_ID
        or payload.get("source_sha") != window_info.get("entry_source_sha")
        or not re.fullmatch(r"[0-9a-f]{40}", str(window_info.get("entry_source_sha", "")))
        or payload.get("total_seconds") != TASK41_TOTAL_SECONDS
        or payload.get("numerical_seconds") != TASK41_NUMERICAL_SECONDS
        or payload.get("closeout_seconds") != TASK41_CLOSEOUT_SECONDS
    ):
        raise Task41ContractError("Task41 execution window identity or time limits changed")
    anchor = payload.get("anchor")
    if not isinstance(anchor, dict) or set(anchor) != {
        "monotonic", "boottime", "utc_ns", "boot_id"
    }:
        raise Task41ContractError("Task41 execution window clock anchor is incomplete")
    try:
        t0_ns = _utc_ns(payload["t0_utc"])
        numerical_deadline_ns = _utc_ns(payload["numerical_deadline_utc"])
        deadline_ns = _utc_ns(payload["deadline_utc"])
    except ValueError as exc:
        raise Task41ContractError(f"Task41 execution window UTC value is invalid: {exc}") from exc
    if (
        anchor["utc_ns"] != t0_ns
        or numerical_deadline_ns != t0_ns + int(TASK41_NUMERICAL_SECONDS * 1e9)
        or deadline_ns != t0_ns + int(TASK41_TOTAL_SECONDS * 1e9)
        or not isinstance(anchor["boot_id"], str)
        or not anchor["boot_id"]
    ):
        raise Task41ContractError("Task41 execution window timestamps are inconsistent")
    if require_current_boot:
        current = clock_sample(include_boot_id=True)
        if current["boot_id"] != anchor["boot_id"]:
            raise Task41ContractError("Task41 execution window belongs to another boot")
        if current["utc_ns"] >= deadline_ns:
            raise Task41ContractError("Task41 fixed execution window has expired")
    accounting_path = _resolve(root, payload["accounting_path"], "accounting_path")
    if not accounting_path.is_relative_to(root / "benchmarks/artifacts/task41extra_phi90_p50x50_g17x20"):
        raise Task41ContractError("Task41 accounting ledger escaped its artifact directory")
    return FixedCampaignWindow(
        path=path,
        sha256=digest,
        payload=payload,
        anchor=anchor,
        t0_utc_ns=t0_ns,
        deadline_utc_ns=deadline_ns,
        total_seconds=TASK41_TOTAL_SECONDS,
        bootstrap_seconds=0.0,
        closeout_seconds=TASK41_CLOSEOUT_SECONDS,
    )


def _task41_window_for_contract(root: Path) -> tuple[FixedCampaignWindow, str, dict[str, Any]]:
    path = (root / TASK41_WINDOW_RELATIVE).resolve()
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise Task41ContractError("Task41 fixed execution window is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise Task41ContractError("Task41 fixed execution window must be a JSON object")
    entry_source = payload.get("source_sha")
    window_contract = {
        "window": {
            "path": str(TASK41_WINDOW_RELATIVE),
            "sha256": digest,
            "entry_source_sha": entry_source,
        }
    }
    window = load_task41_p0_fixed_window(
        window_contract, current_root=root, require_current_boot=True
    )
    return window, digest, payload


def _check_task41_native_receipt(
    abi_receipt_path: Path, runtime_prefix: Path
) -> str:
    try:
        receipt = json.loads(abi_receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Task41ContractError(f"Task41 ABI receipt cannot be read: {exc}") from exc
    petsc = receipt.get("PETSc") if isinstance(receipt, dict) else None
    mpi = receipt.get("MPI") if isinstance(receipt, dict) else None
    if (
        not isinstance(receipt, dict)
        or receipt.get("status") != "IMPORT_SCALAR_MPI_API_PASS_NO_FE_ACTION"
        or receipt.get("runtime_profile") != "native_linux"
        or Path(str(receipt.get("prefix", ""))).resolve() != runtime_prefix.resolve()
        or not isinstance(petsc, dict)
        or petsc.get("scalar_dtype") != "complex128"
        or petsc.get("int_dtype") != "int32"
        or not isinstance(mpi, dict)
        or mpi.get("size") != 1
        or mpi.get("rank") != 0
    ):
        raise Task41ContractError(
            "Task41 ABI receipt must bind native_linux, complex128/int32, and MPI1"
        )
    return hashlib.sha256(abi_receipt_path.read_bytes()).hexdigest()


def prepare_task41_p0(
    *,
    runtime_prefix: str | Path,
    abi_receipt: str | Path,
    jit_cache: str | Path,
    current_root: str | Path | None = None,
) -> dict[str, Any]:
    """Register or reuse the one fixed P0 window, then write a source-bound contract.

    On first use the T0 record is durably created before runtime and input validation.
    Later calls reuse its exact bytes, including when the current source has changed.
    """
    root = Path(current_root or Path(__file__).resolve().parents[2]).resolve()
    source_sha = _git(root, "rev-parse", "HEAD")
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise Task41ContractError("Task41 current HEAD is not a full Git SHA")
    if _git(root, "branch", "--show-current") != TASK41_BRANCH:
        raise Task41ContractError("Task41 P0 prepare requires the registered execution branch")
    if _git(root, "status", "--porcelain", "--untracked-files=normal"):
        raise Task41ContractError("Task41 P0 prepare requires a clean frozen source tree")

    window_path = (root / TASK41_WINDOW_RELATIVE).resolve()
    if not window_path.exists():
        anchor = clock_sample(include_boot_id=True)
        t0_ns = int(anchor["utc_ns"])
        window_payload = {
            "schema": TASK41_P0_WINDOW_SCHEMA,
            "task_id": TASK41_MODEL_ID,
            "source_sha": source_sha,
            "t0_utc": _utc_text_from_ns(t0_ns),
            "numerical_deadline_utc": _utc_text_from_ns(
                t0_ns + int(TASK41_NUMERICAL_SECONDS * 1_000_000_000)
            ),
            "deadline_utc": _utc_text_from_ns(
                t0_ns + int(TASK41_TOTAL_SECONDS * 1_000_000_000)
            ),
            "total_seconds": TASK41_TOTAL_SECONDS,
            "numerical_seconds": TASK41_NUMERICAL_SECONDS,
            "closeout_seconds": TASK41_CLOSEOUT_SECONDS,
            "anchor": anchor,
            "accounting_path": str(
                (root / TASK41_CONTROLLER_RELATIVE / "campaign_accounting_v10.jsonl").resolve()
            ),
        }
        _write_json_no_replace(window_path, window_payload)

    window, window_sha, window_payload = _task41_window_for_contract(root)

    runtime_path = _resolve(root, str(runtime_prefix), "runtime_prefix")
    abi_path = _resolve(root, str(abi_receipt), "abi_receipt")
    jit_path = _resolve(root, str(jit_cache), "jit_cache")
    python_path = runtime_path / "bin" / "python"
    if not runtime_path.is_dir() or not python_path.is_file() or not os.access(python_path, os.X_OK):
        raise Task41ContractError("Task41 native runtime prefix must contain executable bin/python")
    if not abi_path.is_file() or not jit_path.is_dir():
        raise Task41ContractError("Task41 ABI receipt or JIT cache path is missing")
    abi_sha = _check_task41_native_receipt(abi_path, runtime_path)

    input_path = (root / TASK41_INPUT_RELATIVE).resolve()
    try:
        from src.geometry.task41_phi90_profile import task41_payload_errors
        from src.io.execution_plan import resolved_config_bytes
        from src.io.input_validation import load_and_resolve

        specification = load_and_resolve(input_path)
        payload_errors = task41_payload_errors(specification.as_jsonable())
    except (OSError, ValueError, RuntimeError) as exc:
        raise Task41ContractError(f"Task41 registered DAT could not be resolved: {exc}") from exc
    if payload_errors:
        raise Task41ContractError(
            "Task41 registered DAT failed its native physics/profile gate: "
            + "; ".join(payload_errors)
        )
    resolved_sha = hashlib.sha256(resolved_config_bytes(specification)).hexdigest()
    case = {
        "input_path": str(TASK41_INPUT_RELATIVE),
        "input_sha256": specification.input_sha256,
        "model_id": specification.identity.get("model_id"),
        "run_id": specification.identity.get("run_id"),
        "physical_model_sha256": specification.physical_model_sha256,
        "resolved_config_sha256": resolved_sha,
        "method": specification.method.get("kind"),
        "mpi_size": specification.execution.get("mpi_size"),
    }
    validate_task41_specification(specification, input_path, {"case": case}, current_root=root)

    if _git(root, "rev-parse", "HEAD") != source_sha or _git(
        root, "branch", "--show-current"
    ) != TASK41_BRANCH or _git(root, "status", "--porcelain", "--untracked-files=normal"):
        raise Task41ContractError("Task41 source changed while the P0 contract was being prepared")

    contract_path = root / contract_relative_path(source_sha)
    if contract_path.exists():
        raise Task41ContractError("a Task41 contract already exists for this source SHA")
    service_directory = Path(
        "benchmarks/artifacts/task41extra_phi90_p50x50_g17x20/p0_a1"
    ) / f"service_source_{source_sha}"
    contract = {
        "schema": TASK41_P0_CONTRACT_SCHEMA,
        "task_id": TASK41_MODEL_ID,
        "branch": TASK41_BRANCH,
        "source": {"sha": source_sha},
        "case": case,
        "runtime": {
            "profile": "native_linux",
            "runtime_prefix": str(runtime_path),
            "abi_receipt_path": str(abi_path),
            "abi_receipt_sha256": abi_sha,
            "jit_cache": str(jit_path),
            "mpi_ranks": 1,
            "math_threads": 1,
        },
        "window": {
            "path": str(TASK41_WINDOW_RELATIVE),
            "sha256": window_sha,
            "entry_source_sha": window_payload["source_sha"],
        },
        "resources": {
            "task_memory_max_bytes": TASK41_TASK_MEMORY_MAX_BYTES,
            "host_reserve_bytes": TASK41_HOST_RESERVE_BYTES,
            "memory_swap_max_bytes": 0,
        },
        "time": {
            "total_seconds": TASK41_TOTAL_SECONDS,
            "numerical_seconds": TASK41_NUMERICAL_SECONDS,
            "closeout_seconds": TASK41_CLOSEOUT_SECONDS,
        },
        "evidence": {"service_directory": str(service_directory)},
    }
    if not _write_json_no_replace(contract_path, contract):
        raise Task41ContractError("a Task41 contract was concurrently created for this source SHA")
    contract_sha = sha256_file(contract_path)
    return {
        "contract_path": str(contract_path.relative_to(root)),
        "contract_sha256": contract_sha,
        "window_path": str(window_path.relative_to(root)),
        "window_sha256": window_sha,
        "window_t0_utc": window_payload["t0_utc"],
        "window_entry_source_sha": window_payload["source_sha"],
        "contract_source_sha": source_sha,
        "resolved_config_sha256": resolved_sha,
        "service_command": [
            "bash",
            "scripts/run_case_in_user_service.sh",
            str(TASK41_INPUT_RELATIVE),
            "--task41-p0-execution-contract",
            str(contract_path.relative_to(root)),
        ],
    }


def validate_task41_specification(
    specification: Any, input_path: str | Path, contract: Mapping[str, Any],
    *, current_root: str | Path | None = None,
) -> None:
    root = Path(current_root or Path(__file__).resolve().parents[2]).resolve()
    case = contract["case"]
    actual_input = Path(input_path).resolve()
    expected_input = _resolve(root, case["input_path"], "case.input_path")
    from src.io.execution_plan import resolved_config_bytes

    resolved_sha = hashlib.sha256(resolved_config_bytes(specification)).hexdigest()
    if (
        actual_input != expected_input
        or sha256_file(actual_input) != case["input_sha256"]
        or specification.identity.get("model_id") != case["model_id"]
        or specification.identity.get("run_id") != case["run_id"]
        or specification.method.get("kind") != case["method"]
        or specification.execution.get("mpi_size") != case["mpi_size"]
        or specification.physical_model_sha256 != case["physical_model_sha256"]
        or resolved_sha != case["resolved_config_sha256"]
    ):
        raise Task41ContractError("resolved Task41 input differs from the frozen P0 contract")


def launcher_values(contract_path: str | Path, *, current_root: str | Path | None = None) -> list[str]:
    root = Path(current_root or Path(__file__).resolve().parents[2]).resolve()
    contract, digest = require_task41_p0_contract(
        contract_path, current_root=root, check_current_source=True, require_clean_source=True
    )
    window = load_task41_p0_fixed_window(contract, current_root=root, require_current_boot=True)
    runtime = contract["runtime"]
    resources = contract["resources"]
    case = contract["case"]
    return [
        str(root),
        str(_resolve(root, runtime["runtime_prefix"], "runtime_prefix")),
        str(_resolve(root, runtime["abi_receipt_path"], "abi_receipt_path")),
        str(_resolve(root, runtime["jit_cache"], "jit_cache")),
        digest,
        str(window.path),
        window.sha256,
        str(resources["task_memory_max_bytes"]),
        str(resources["host_reserve_bytes"]),
        str(resources["memory_swap_max_bytes"]),
        str(_resolve(root, case["input_path"], "case.input_path")),
        str(contract["source"]["sha"]),
    ]


def qualified_activation_identity(environment: Mapping[str, str]) -> str | None:
    if environment.get("TASK41_P0_STRICT_EXECUTION") != "1":
        return None
    root = Path(__file__).resolve().parents[2]
    contract_path = environment.get("TASK41_P0_CONTRACT_PATH")
    contract_sha = environment.get("TASK41_P0_CONTRACT_SHA256")
    try:
        contract, digest = require_task41_p0_contract(
            contract_path or "",
            expected_sha256=contract_sha,
            current_root=root,
            check_current_source=True,
            require_clean_source=True,
        )
        runtime = _resolve(root, contract["runtime"]["runtime_prefix"], "runtime_prefix")
        if (
            digest != contract_sha
            or environment.get("_MYFENICS_CLOUD_QUALIFIED_ACTIVATION") != "1"
            or environment.get("_MYFENICS_CLOUD_RUNTIME_PROFILE") != "native_linux"
            or environment.get("_MYFENICS_CLOUD_ABI_MANIFEST_SHA256")
            != contract["runtime"]["abi_receipt_sha256"]
            or not Path(sys.executable).resolve().is_relative_to(runtime)
            or environment.get("TASK41_P0_EXPECTED_SOURCE_SHA")
            != contract["source"]["sha"]
        ):
            return None
        return f"task41_p0_native_complex:{contract['runtime']['abi_receipt_sha256']}"
    except (OSError, ValueError, RuntimeError):
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--launcher-values", action="store_true")
    mode.add_argument("--prepare", action="store_true")
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--runtime-prefix", type=Path)
    parser.add_argument("--abi-receipt", type=Path)
    parser.add_argument("--jit-cache", type=Path)
    args = parser.parse_args(argv)
    if args.launcher_values:
        if args.contract is None:
            parser.error("--launcher-values requires --contract")
        for value in launcher_values(args.contract):
            print(value)
        return 0
    if args.prepare:
        missing = [
            name
            for name in ("runtime_prefix", "abi_receipt", "jit_cache")
            if getattr(args, name) is None
        ]
        if missing:
            parser.error("--prepare requires --runtime-prefix, --abi-receipt, and --jit-cache")
        result = prepare_task41_p0(
            runtime_prefix=args.runtime_prefix,
            abi_receipt=args.abi_receipt,
            jit_cache=args.jit_cache,
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
