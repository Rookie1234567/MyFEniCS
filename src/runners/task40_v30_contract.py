"""Fail-closed V30 execution contract for the all-q reference campaign."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import socket
import sys
from typing import Any, Mapping

from src.runners.task40_v10_campaign import (
    TASK40_V30_CAMPAIGN_ID,
    TASK40_V30_CAMPAIGN_SECONDS,
    TASK40_V30_CLOSEOUT_RESERVE_SECONDS,
    TASK40_V30_REVIEW_COMMIT,
    TASK40_V30_REVIEW_PATH,
    TASK40_V30_REVIEW_SHA256,
    TASK40_V30_SOURCE_AT_ENTRY,
    TASK40_V30_STAGE_SCOPE,
    TASK40_V30_TARGET_CAMPAIGN_SHA256,
    TASK40_V30_TARGET_CAMPAIGN_WINDOW,
    load_fixed_campaign_window,
)
from src.runners.task40_v29_contract import read_json_object, sha256_file


V30_CONTRACT_SCHEMA = "task40extra.review_v30_execution_contract.v1"
V30_SCOPE = "V30_ALL_Q_REFERENCE_WITH_CONDITIONAL_TARGET_PILOT"
V30_EXECUTION_ROOT = Path("/home/fenics/Projects/laptop_share")
V30_RUNTIME_RELATIVE = Path(
    "benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/runtime_prefix"
)
V30_ABI_RECEIPT_RELATIVE = Path(
    "benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/continuation_attempt4/abi_receipt.json"
)
V30_JIT_CACHE_RELATIVE = Path(
    "benchmarks/artifacts/task40extra_0p7nm_engineering/local_w9_wsl/window_qualification_jit"
)
V30_WINDOW_RELATIVE = TASK40_V30_TARGET_CAMPAIGN_WINDOW
V30_TARGET_HOST = "fenics-ws"
V30_TARGET_HOSTNAME = "fenics-ws01"
V30_TARGET_BOOT_ID = "fd8f4b00-1e17-46af-a6fa-da3a32dbeba3"
V30_ABI_RECEIPT_SHA256 = "1c4277c83a0ac6daf02197086264b9e5b337caee1b33d7cc1dd22a7dfcefe57d"
V30_Q0_DONOR = {
    "identity_sha256": "5bcddb4ddc01d7092ec535eed1fab24a15add33f3f6c56b5aca4cb4f358e858c",
    "manifest_relative_path": (
        "results/task40extra_nonseparable_0p7nm/"
        "task40extra_0p7nm_target_original_ny8_operator_probe_v22__full3d_iterative__mpi1__Mna/"
        "20261011T153931.649307Z/v27_q0_csr/task40_v28_q0_csr_continuation_manifest.json"
    ),
    "manifest_sha256": "ca3c8de9093fd1cfe9e17c8eb557cd2f96920a3ee110549f007e70835d4a2290",
    "native_qualification_relative_path": (
        "results/task40extra_nonseparable_0p7nm/"
        "task40extra_0p7nm_target_original_ny8_operator_probe_v22__full3d_iterative__mpi1__Mna/"
        "20261012T002559.817050Z/v28_q0_native_qualification.json"
    ),
    "native_qualification_status": "PASS_COMPLETE_Q0_CSR_NATIVE_READBACK",
    "native_qualification_sha256": "63babb2943b7e0f613a2c531afd09f931c4ee5504a345748c52f6ef38b0e9c81",
}
V30_Q_CSR_WORKLIST = [
    {"q": 4, "action": "reuse_twist0_saved_stream_build_own_q4_csr_and_native"},
    {"q": 1, "action": "prepare_twist1_once_build_own_q1_csr_and_native"},
    {"q": 5, "action": "reuse_twist1_prepare_build_own_q5_csr_and_native"},
    {"q": 2, "action": "prepare_twist2_once_build_own_q2_csr_and_native"},
    {"q": 6, "action": "reuse_twist2_prepare_build_own_q6_csr_and_native"},
    {"q": 3, "action": "prepare_twist3_once_build_own_q3_csr_and_native"},
    {"q": 7, "action": "reuse_twist3_prepare_build_own_q7_csr_and_native"},
]
V30_RESOURCES = {
    "task_memory_max_bytes": 1_649_267_441_664,
    "host_reserve_bytes": 68_719_476_736,
    "memory_swap_max_bytes": 0,
    "mpi_ranks": 1,
    "math_threads": 1,
}


class V30ContractError(ValueError):
    """A V30 execution contract or live resource gate failed closed."""


def _rooted_path(root: Path, value: str | Path, label: str) -> Path:
    supplied = Path(value)
    candidate = (supplied if supplied.is_absolute() else root / supplied).resolve()
    if not candidate.is_relative_to(root):
        raise V30ContractError(f"V30 {label} escapes the approved execution root: {candidate}")
    return candidate


def require_authorized_contract(
    path: str | Path,
    *,
    expected_sha256: str | None = None,
    current_root: str | Path | None = None,
    require_current_boot: bool = True,
    current_hostname: str | None = None,
) -> tuple[dict[str, Any], str]:
    """Validate the approved V30 scope, target-native window, runtime and limits."""
    contract_path = Path(path).resolve()
    if not contract_path.is_file():
        raise V30ContractError(f"V30 execution contract is missing: {contract_path}")
    digest = sha256_file(contract_path)
    if expected_sha256 is not None and digest != expected_sha256:
        raise V30ContractError(
            f"V30 contract hash mismatch: expected {expected_sha256}, got {digest}"
        )
    contract = read_json_object(contract_path)
    if contract.get("schema") != V30_CONTRACT_SCHEMA:
        raise V30ContractError("V30 execution contract schema is unsupported")
    if contract.get("authorization_status") != "USER_APPROVED":
        raise V30ContractError("V30 launch held: execution contract is not user-approved")
    if (
        contract.get("scope") != V30_SCOPE
        or contract.get("campaign") != TASK40_V30_CAMPAIGN_ID
        or contract.get("review_commit") != TASK40_V30_REVIEW_COMMIT
        or contract.get("review_path") != TASK40_V30_REVIEW_PATH
        or contract.get("review_sha256") != TASK40_V30_REVIEW_SHA256
        or contract.get("source_at_entry") != TASK40_V30_SOURCE_AT_ENTRY
    ):
        raise V30ContractError("V30 contract scope or active-review identity differs")
    if contract.get("campaign_stage_scope") != list(TASK40_V30_STAGE_SCOPE):
        raise V30ContractError("V30 contract campaign stage scope differs from Review V30")
    preparation = contract.get("preparation")
    if not isinstance(preparation, Mapping) or (
        preparation.get("accepted_q0_donor") != V30_Q0_DONOR
        or preparation.get("q_csr_worklist") != V30_Q_CSR_WORKLIST
        or preparation.get("final_all_q_selector_required_at")
        != "P3_all_q_resident_factor_bank"
    ):
        raise V30ContractError(
            "V30 preparation must bind the accepted q0 donor and defer the all-q selector until factor-bank entry"
        )
    donor_manifest = _rooted_path(
        V30_EXECUTION_ROOT,
        preparation["accepted_q0_donor"]["manifest_relative_path"],
        "accepted q0 donor manifest",
    )
    donor_qualification = _rooted_path(
        V30_EXECUTION_ROOT,
        preparation["accepted_q0_donor"]["native_qualification_relative_path"],
        "accepted q0 native qualification",
    )
    if (
        not donor_manifest.is_file()
        or sha256_file(donor_manifest) != V30_Q0_DONOR["manifest_sha256"]
        or not donor_qualification.is_file()
        or sha256_file(donor_qualification)
        != V30_Q0_DONOR["native_qualification_sha256"]
    ):
        raise V30ContractError("V30 accepted q0 donor manifest or native qualification changed")
    execution = contract.get("execution")
    if not isinstance(execution, Mapping):
        raise V30ContractError("V30 execution fields are missing")
    root = Path(str(execution.get("execution_root", ""))).resolve()
    if root != V30_EXECUTION_ROOT or not root.is_absolute():
        raise V30ContractError("V30 execution root differs from the approved workstation root")
    if current_root is not None and root != Path(current_root).resolve():
        raise V30ContractError(
            f"V30 execution root differs from the service root: {root} != {Path(current_root).resolve()}"
        )
    host = execution.get("host_identity")
    if (
        execution.get("execution_host") != V30_TARGET_HOST
        or not isinstance(host, Mapping)
        or host.get("hostname") != V30_TARGET_HOSTNAME
        or host.get("runtime_profile") != "native_linux"
        or host.get("boot_id") != V30_TARGET_BOOT_ID
    ):
        raise V30ContractError("V30 target host, native runtime, or boot identity differs")
    if current_hostname is not None and current_hostname.split(".", 1)[0] != V30_TARGET_HOSTNAME:
        raise V30ContractError(f"V30 contract must run on {V30_TARGET_HOSTNAME}, got {current_hostname}")
    approval = contract.get("user_approval")
    if not isinstance(approval, Mapping) or (
        approval.get("scope") != V30_SCOPE
        or approval.get("execution_host") != V30_TARGET_HOST
        or approval.get("execution_root") != str(V30_EXECUTION_ROOT)
        or approval.get("resources") != V30_RESOURCES
    ):
        raise V30ContractError("V30 user approval does not match the fixed resource package")
    resources = execution.get("resources")
    if not isinstance(resources, Mapping) or dict(resources) != V30_RESOURCES:
        raise V30ContractError("V30 execution resources differ from the approved package")
    window_spec = execution.get("window")
    if not isinstance(window_spec, Mapping) or dict(window_spec) != {
        "total_seconds": TASK40_V30_CAMPAIGN_SECONDS,
        "numeric_cutoff_after_t0_seconds": 42_000.0,
        "closeout_reserve_seconds": TASK40_V30_CLOSEOUT_RESERVE_SECONDS,
        "t0_utc": "2026-10-12T12:23:42.000Z",
    }:
        raise V30ContractError("V30 fixed campaign window or cutoff differs")
    if execution.get("scalar_type") != "complex128" or execution.get("index_type") != "int32":
        raise V30ContractError("V30 ABI must remain complex128/int32")

    runtime = _rooted_path(root, str(execution.get("runtime_prefix", "")), "runtime")
    abi_receipt = _rooted_path(root, str(execution.get("abi_receipt_path", "")), "ABI receipt")
    jit_cache = _rooted_path(root, str(execution.get("jit_cache", "")), "JIT cache")
    window_path = _rooted_path(root, str(execution.get("campaign_window_path", "")), "campaign window")
    expected_paths = {
        "runtime_prefix": (root / V30_RUNTIME_RELATIVE).resolve(),
        "abi_receipt_path": (root / V30_ABI_RECEIPT_RELATIVE).resolve(),
        "jit_cache": (root / V30_JIT_CACHE_RELATIVE).resolve(),
        "campaign_window_path": (root / V30_WINDOW_RELATIVE).resolve(),
    }
    actual_paths = {
        "runtime_prefix": runtime,
        "abi_receipt_path": abi_receipt,
        "jit_cache": jit_cache,
        "campaign_window_path": window_path,
    }
    if actual_paths != expected_paths:
        raise V30ContractError("V30 runtime/receipt/JIT/window path identity differs")
    if not runtime.is_dir() or not (runtime / "bin/python").is_file():
        raise V30ContractError(f"V30 qualified runtime is unavailable: {runtime}")
    if not abi_receipt.is_file() or sha256_file(abi_receipt) != V30_ABI_RECEIPT_SHA256:
        raise V30ContractError(f"V30 ABI receipt is missing or changed: {abi_receipt}")
    if not jit_cache.is_dir():
        raise V30ContractError(f"V30 qualified JIT cache is unavailable: {jit_cache}")
    if execution.get("abi_receipt_sha256") != V30_ABI_RECEIPT_SHA256:
        raise V30ContractError("V30 ABI receipt hash differs from the qualified target identity")
    if (
        execution.get("campaign_window_sha256") != TASK40_V30_TARGET_CAMPAIGN_SHA256
        or not window_path.is_file()
        or sha256_file(window_path) != TASK40_V30_TARGET_CAMPAIGN_SHA256
    ):
        raise V30ContractError("V30 target-native campaign window is missing or changed")
    window_payload = read_json_object(window_path)
    try:
        validated_window = load_fixed_campaign_window(
            window_path, require_current_boot=require_current_boot
        )
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise V30ContractError(f"V30 target-native campaign window failed validation: {error}") from error
    if (
        validated_window.sha256 != TASK40_V30_TARGET_CAMPAIGN_SHA256
        or window_payload.get("stage_scope") != list(TASK40_V30_STAGE_SCOPE)
        or window_payload.get("initial_boot_id") != V30_TARGET_BOOT_ID
        or window_payload.get("user_approval") != dict(approval)
        or window_payload.get("target_clock_receipt_sha256")
        != "079a2031f16abe1d3eaf2a122801351670278d9007235b1705e0846e45920ae4"
    ):
        raise V30ContractError("V30 contract and target-native window/approval differ")
    if contract_path.parent.resolve() != (root / V30_WINDOW_RELATIVE).resolve().parent:
        raise V30ContractError("V30 execution contract must be colocated with its target window")
    return contract, digest


def qualified_activation_identity(environment: Mapping[str, str]) -> str | None:
    """Require the reviewed native-linux activation for V30 service children."""
    if environment.get("TASK40_V30_STRICT_EXECUTION") != "1":
        return None
    digest = environment.get("_MYFENICS_CLOUD_ABI_MANIFEST_SHA256", "")
    if (
        environment.get("_MYFENICS_CLOUD_QUALIFIED_ACTIVATION") == "1"
        and environment.get("_MYFENICS_CLOUD_RUNTIME_PROFILE") == "native_linux"
        and environment.get("_MYFENICS_CLOUD_QUALIFICATION_SCOPE")
        == "imports_only_C1_FE_JIT_NOT_RUN"
        and re.fullmatch(r"[0-9a-f]{64}", digest)
    ):
        return f"native_linux_imports_only:{digest}"
    return None


def validate_live_resource_contract(
    contract: Mapping[str, Any],
    *,
    cgroup_limit_bytes: int,
    cgroup_current_bytes: int,
    cgroup_swap_current_bytes: int,
    host_effective_available_bytes: int,
    additional_request_bytes: int,
) -> dict[str, int | bool]:
    execution = contract.get("execution")
    resources = execution.get("resources") if isinstance(execution, Mapping) else None
    if not isinstance(resources, Mapping) or dict(resources) != V30_RESOURCES:
        raise V30ContractError("V30 live resource gate has no exact approved limits")
    cap = int(resources["task_memory_max_bytes"])
    reserve = int(resources["host_reserve_bytes"])
    request = int(additional_request_bytes)
    if int(cgroup_limit_bytes) != cap:
        raise V30ContractError(f"V30 cgroup cap differs from contract: expected {cap}, got {cgroup_limit_bytes}")
    if int(cgroup_swap_current_bytes) != 0:
        raise V30ContractError("V30 task cgroup swap must remain zero")
    if int(cgroup_current_bytes) + request > cap:
        raise V30ContractError("V30 task memory admission exceeds the fixed campaign cap")
    if int(host_effective_available_bytes) - request < reserve:
        raise V30ContractError("V30 host memory admission would consume the approved host reserve")
    return {
        "passed": True,
        "task_memory_max_bytes": cap,
        "host_reserve_bytes": reserve,
        "memory_swap_max_bytes": 0,
        "cgroup_current_bytes": int(cgroup_current_bytes),
        "additional_request_bytes": request,
        "host_effective_available_bytes": int(host_effective_available_bytes),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--launcher-values", action="store_true")
    parser.add_argument("--contract", required=True)
    parser.add_argument("--expected-sha256")
    args = parser.parse_args(argv)
    try:
        contract, contract_sha = require_authorized_contract(
            args.contract,
            expected_sha256=args.expected_sha256,
            current_root=Path(__file__).resolve().parents[2],
            current_hostname=socket.gethostname(),
        )
        execution = contract["execution"]
        if args.launcher_values:
            values = (
                str(execution["execution_root"]),
                str(_rooted_path(V30_EXECUTION_ROOT, execution["runtime_prefix"], "runtime")),
                str(_rooted_path(V30_EXECUTION_ROOT, execution["abi_receipt_path"], "ABI receipt")),
                str(_rooted_path(V30_EXECUTION_ROOT, execution["jit_cache"], "JIT cache")),
                str(V30_RESOURCES["task_memory_max_bytes"]),
                contract_sha,
                str(_rooted_path(V30_EXECUTION_ROOT, execution["campaign_window_path"], "campaign window")),
                TASK40_V30_TARGET_CAMPAIGN_SHA256,
                str(V30_RESOURCES["host_reserve_bytes"]),
                str(V30_RESOURCES["memory_swap_max_bytes"]),
            )
            sys.stdout.write("\n".join(values) + "\n")
        else:
            print(json.dumps({"status": "V30_AUTHORIZED", "contract_sha256": contract_sha}))
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
