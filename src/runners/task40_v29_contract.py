"""Fail-closed execution contract and path binding for the V29 q0 factor run."""
from __future__ import annotations

from hashlib import sha256
import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping

from src.runners.task40_v10_campaign import (
    TASK40_V29_CAMPAIGN_SECONDS,
    TASK40_V29_CLOSEOUT_RESERVE_SECONDS,
    TASK40_V29_REVIEW_COMMIT,
    TASK40_V29_REVIEW_PATH,
    TASK40_V29_REVIEW_SHA256,
    load_fixed_campaign_window,
)


V29_CONTRACT_SCHEMA = "task40extra.review_v29_execution_contract.v1"
V29_SELECTOR_SCHEMA = "task40extra.review_v29_factor_only_selector.v1"
V29_STRICT_POLICY = "COMPLETE_AND_MATCHING_V28_NATIVE_PASS_REQUIRED"
SOURCE_ROOT = Path("/home/shenjh/Projects/MyFEniCSx_task40extra_0p7nm_engineering")
APPROVED_EXECUTION_ROOT = Path("/home/fenics/Projects/laptop_share")


def qualified_activation_identity(environment: Mapping[str, str]) -> str | None:
    """Return the runtime profile identity without treating native Linux as WSL."""
    if environment.get("TASK40_V29_STRICT_FACTOR_ONLY") == "1":
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
    if environment.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") == "1":
        return "1"
    return None


class V29ContractError(ValueError):
    """A V29 contract or immutable scientific input failed validation."""


def sha256_file(path: str | Path) -> str:
    digest = sha256()
    with Path(path).open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def read_json_object(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    value = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise V29ContractError(f"{target}: expected a JSON object")
    return value


def contract_fingerprint(path: str | Path) -> str:
    return sha256_file(path)


def require_authorized_contract(
    path: str | Path,
    *,
    expected_sha256: str | None = None,
    current_root: str | Path | None = None,
) -> tuple[dict[str, Any], str]:
    """Return an authorized V29 contract; a proposal can never pass this gate."""
    contract_path = Path(path).resolve()
    if not contract_path.is_file():
        raise V29ContractError(f"V29 execution contract is missing: {contract_path}")
    digest = sha256_file(contract_path)
    if expected_sha256 is not None and digest != expected_sha256:
        raise V29ContractError(
            f"V29 contract hash mismatch at {contract_path}: expected {expected_sha256}, got {digest}"
        )
    value = read_json_object(contract_path)
    if value.get("schema") != V29_CONTRACT_SCHEMA:
        raise V29ContractError(f"{contract_path}: unsupported schema {value.get('schema')!r}")
    if value.get("authorization_status") != "USER_APPROVED":
        raise V29ContractError(
            "V29 launch held: authorization_status is "
            f"{value.get('authorization_status')!r}; host, Task40 root, resource limits, "
            "runtime/ABI, transfer destinations, and the new fixed window must be explicitly approved"
        )
    approval = value.get("user_approval")
    if not isinstance(approval, Mapping) or approval.get("scope") != "V29_Q0_FACTOR_ONLY":
        raise V29ContractError("V29 launch held: missing explicit user_approval scope")
    if (
        value.get("review_v29_commit") != TASK40_V29_REVIEW_COMMIT
        or value.get("review_v29_sha256") != TASK40_V29_REVIEW_SHA256
    ):
        raise V29ContractError("V29 launch held: execution contract is not bound to the active Review V29")
    source_at_entry = value.get("source_at_entry")
    if not isinstance(source_at_entry, str) or not re.fullmatch(
        r"[0-9a-f]{40,64}", source_at_entry
    ):
        raise V29ContractError("V29 launch held: frozen source_at_entry is missing or malformed")
    execution = value.get("execution")
    if not isinstance(execution, Mapping):
        raise V29ContractError("V29 launch held: execution fields are missing")
    required = (
        "execution_host",
        "host_identity",
        "execution_root",
        "runtime_prefix",
        "abi_receipt_path",
        "abi_receipt_sha256",
        "jit_cache",
        "campaign_window_path",
        "campaign_window_sha256",
        "t0_utc",
    )
    missing = [name for name in required if execution.get(name) in (None, "")]
    if missing:
        raise V29ContractError("V29 launch held: unresolved execution fields: " + ", ".join(missing))
    host_identity = execution.get("host_identity")
    if (
        execution.get("execution_host") != "fenics-ws"
        or not isinstance(host_identity, Mapping)
        or host_identity.get("address") != "10.14.35.46"
        or host_identity.get("remote_user") != "fenics"
    ):
        raise V29ContractError("V29 launch held: execution host identity differs from the user-approved target")
    resources = execution.get("resources")
    if not isinstance(resources, Mapping):
        raise V29ContractError("V29 launch held: approved resource contract is missing")
    approved_resources = approval.get("resources")
    if not isinstance(approved_resources, Mapping) or dict(resources) != dict(approved_resources):
        raise V29ContractError("V29 launch held: execution resources do not exactly match explicit user approval")
    for name in ("task_memory_max_bytes", "host_reserve_bytes"):
        if type(resources.get(name)) is not int or resources[name] <= 0:
            raise V29ContractError(f"V29 launch held: approved {name} must be a positive integer")
    if resources.get("memory_swap_max_bytes") != 0 or resources.get("mpi_ranks") != 1 or resources.get("math_threads") != 1:
        raise V29ContractError("V29 launch held: swap/MPI/thread contract differs from the approved single-rank proposal")
    if execution.get("scalar_type") != "complex128" or execution.get("index_type") != "int32":
        raise V29ContractError("V29 launch held: target ABI must be explicitly qualified complex128/int32")
    window = execution.get("window")
    if not isinstance(window, Mapping) or (
        window.get("total_seconds") != 21_600
        or window.get("numeric_cutoff_after_t0_seconds") != 20_400
        or window.get("closeout_reserve_seconds") != 1_200
        or window.get("t0_utc") != execution.get("t0_utc")
    ):
        raise V29ContractError("V29 launch held: a new fixed 6-hour window has not been frozen")
    root_value = Path(str(execution["execution_root"])).resolve()
    if not root_value.is_absolute() or not root_value.is_dir():
        raise V29ContractError(f"V29 execution root is unavailable: {root_value}")
    if root_value != APPROVED_EXECUTION_ROOT:
        raise V29ContractError(f"V29 execution root must be the explicitly approved empty destination: {APPROVED_EXECUTION_ROOT}")
    if current_root is not None and root_value != Path(current_root).resolve():
        raise V29ContractError(
            f"V29 execution root differs from this process root: {root_value} != {Path(current_root).resolve()}"
        )
    runtime = Path(str(execution["runtime_prefix"])).resolve()
    abi_receipt = Path(str(execution["abi_receipt_path"])).resolve()
    jit_cache = Path(str(execution["jit_cache"])).resolve()
    for label, candidate in (("runtime_prefix", runtime), ("abi_receipt_path", abi_receipt), ("jit_cache", jit_cache)):
        if not candidate.is_relative_to(root_value):
            raise V29ContractError(f"V29 {label} must remain under the approved execution root: {candidate}")
    if not runtime.is_dir() or not (runtime / "bin/python").is_file():
        raise V29ContractError(f"V29 target runtime is unavailable: {runtime}")
    if not abi_receipt.is_file() or sha256_file(abi_receipt) != execution["abi_receipt_sha256"]:
        raise V29ContractError(f"V29 ABI receipt is missing or changed: {abi_receipt}")
    if not jit_cache.is_dir():
        raise V29ContractError(f"V29 qualified JIT cache is unavailable: {jit_cache}")
    window_path = Path(str(execution["campaign_window_path"])).resolve()
    if not window_path.is_relative_to(root_value):
        raise V29ContractError(f"V29 campaign window must remain under the approved execution root: {window_path}")
    if not window_path.is_file() or sha256_file(window_path) != execution["campaign_window_sha256"]:
        raise V29ContractError(f"V29 campaign window is missing or changed: {window_path}")
    window_payload = read_json_object(window_path)
    validated_window = load_fixed_campaign_window(window_path, require_current_boot=True)
    window_approval_sha = sha256(
        json.dumps(approval, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if (
        window_payload.get("t0_utc") != execution["t0_utc"]
        or window_payload.get("source_at_entry") != source_at_entry
        or window_payload.get("active_review_sha") != TASK40_V29_REVIEW_COMMIT
        or window_payload.get("active_review_path") != TASK40_V29_REVIEW_PATH
        or window_payload.get("active_review_sha256") != TASK40_V29_REVIEW_SHA256
        or window_payload.get("review_at_registration") != TASK40_V29_REVIEW_COMMIT
        or window_payload.get("user_approval") != dict(approval)
        or window_payload.get("user_approval_sha256") != window_approval_sha
        or window_payload.get("campaign_seconds") != TASK40_V29_CAMPAIGN_SECONDS
        or window_payload.get("closeout_reserve_seconds") != TASK40_V29_CLOSEOUT_RESERVE_SECONDS
        or execution["window"].get("total_seconds") != TASK40_V29_CAMPAIGN_SECONDS
        or execution["window"].get("closeout_reserve_seconds") != TASK40_V29_CLOSEOUT_RESERVE_SECONDS
        or validated_window.sha256 != execution["campaign_window_sha256"]
    ):
        raise V29ContractError(
            f"V29 campaign window review/approval/source/duration differs from the approved contract: {window_path}"
        )
    mapping = execution.get("approved_path_mapping")
    if not isinstance(mapping, Mapping) or (
        Path(str(mapping.get("source_root", ""))).resolve() != SOURCE_ROOT
        or Path(str(mapping.get("execution_root", ""))).resolve() != root_value
    ):
        raise V29ContractError("V29 launch held: approved path mapping must preserve the canonical Task40 root layout")
    destinations = execution.get("artifact_destinations")
    if not isinstance(destinations, Mapping):
        raise V29ContractError("V29 launch held: artifact destinations are not explicitly bound")
    for label, raw_path in destinations.items():
        target = Path(str(raw_path)).resolve()
        if not target.is_relative_to(root_value):
            raise V29ContractError(f"V29 artifact destination {label} escapes the approved root: {target}")
    return value, digest


def resolve_approved_path(
    recorded_path: str | Path,
    *,
    source_root: str | Path,
    execution_root: str | Path,
) -> Path:
    """Map one Task40-rooted path without permitting traversal or arbitrary roots."""
    source = Path(source_root).resolve()
    target = Path(execution_root).resolve()
    supplied = Path(recorded_path)
    candidate = supplied.resolve(strict=False) if supplied.is_absolute() else (source / supplied).resolve(strict=False)
    try:
        relative = candidate.relative_to(source)
    except ValueError as exc:
        raise V29ContractError(f"path is outside the approved source Task40 root: {recorded_path}") from exc
    mapped = (target / relative).resolve(strict=False)
    try:
        mapped.relative_to(target)
    except ValueError as exc:
        raise V29ContractError(f"mapped path escapes the approved execution root: {mapped}") from exc
    return mapped


def approved_path_resolver(contract: Mapping[str, Any]):
    """Return the one source-root to execution-root resolver in an approved contract."""
    execution = contract.get("execution")
    mapping = execution.get("approved_path_mapping") if isinstance(execution, Mapping) else None
    if not isinstance(mapping, Mapping):
        raise V29ContractError("V29 contract has no approved source-to-execution path mapping")
    source_root = Path(str(mapping.get("source_root", ""))).resolve()
    execution_root = Path(str(mapping.get("execution_root", ""))).resolve()
    declared_execution_root = Path(str(execution.get("execution_root", ""))).resolve()
    if source_root != SOURCE_ROOT or execution_root != declared_execution_root:
        raise V29ContractError("V29 path mapping must bind the canonical Task40 source root to the approved execution root")

    def resolve(path: str | Path) -> Path:
        return resolve_approved_path(
            path,
            source_root=source_root,
            execution_root=execution_root,
        )

    return resolve


def require_authorized_selector(
    path: str | Path,
    *,
    expected_sha256: str | None,
    contract_path: str | Path,
    contract_sha256: str,
    contract: Mapping[str, Any],
) -> tuple[dict[str, Any], str]:
    """Require one user-approved selector bound to the exact execution contract."""
    selector_path = Path(path).resolve()
    if not selector_path.is_file():
        raise V29ContractError(f"V29 factor-only selector is missing: {selector_path}")
    digest = sha256_file(selector_path)
    if expected_sha256 is not None and digest != expected_sha256:
        raise V29ContractError(
            f"V29 selector hash mismatch at {selector_path}: expected {expected_sha256}, got {digest}"
        )
    selector = read_json_object(selector_path)
    if selector.get("schema") != V29_SELECTOR_SCHEMA:
        raise V29ContractError("V29 factor-only selector schema is unsupported")
    if selector.get("authorization_status") != "USER_APPROVED" or selector.get("status") != "READY":
        raise V29ContractError("V29 launch held: factor-only selector is not user-approved and READY")
    if selector.get("policy") != V29_STRICT_POLICY or selector.get("operation") != "EXISTING_COMPLETE_Q0_CSR_FACTOR_ONLY":
        raise V29ContractError("V29 selector does not request the strict existing-q0 factor-only route")
    if selector.get("execution_contract_sha256") != contract_sha256:
        raise V29ContractError("V29 selector is not bound to the exact authorized execution contract hash")
    resolver = approved_path_resolver(contract)
    mapped_contract_path = resolver(selector.get("execution_contract_path", ""))
    if mapped_contract_path != Path(contract_path).resolve():
        raise V29ContractError("V29 selector execution contract path differs from the approved contract")
    if selector.get("fill_fallback") is not False or selector.get("readback_fallback") is not False:
        raise V29ContractError("V29 strict selector must disable fill and readback fallback")
    return selector, digest


def verify_file_record(
    path: str | Path,
    *,
    expected_bytes: int,
    expected_sha256: str,
    purpose: str,
) -> dict[str, Any]:
    target = Path(path).resolve()
    if not target.is_file():
        raise V29ContractError(f"{purpose}: file is missing: {target}")
    size = target.stat().st_size
    if size != int(expected_bytes):
        raise V29ContractError(f"{purpose}: size mismatch at {target}: expected {expected_bytes}, got {size}")
    actual = sha256_file(target)
    if actual != expected_sha256:
        raise V29ContractError(f"{purpose}: SHA-256 mismatch at {target}: expected {expected_sha256}, got {actual}")
    return {"path": str(target), "bytes": size, "sha256": actual, "purpose": purpose}


def require_strict_factor_only_status(manifest: Mapping[str, Any], qualification: Mapping[str, Any]) -> None:
    """Never turn an incomplete or unqualified manifest into AUTO fill/readback."""
    differences: list[str] = []
    if manifest.get("status") != "COMPLETE_CSR":
        differences.append(f"manifest.status expected COMPLETE_CSR, got {manifest.get('status')!r}")
    if qualification.get("status") != "PASS_COMPLETE_Q0_CSR_NATIVE_READBACK":
        differences.append(
            "qualification.status expected PASS_COMPLETE_Q0_CSR_NATIVE_READBACK, "
            f"got {qualification.get('status')!r}"
        )
    if differences:
        raise V29ContractError("V29 strict factor-only refused before adapter/fill/readback: " + "; ".join(differences))


def validate_live_resource_contract(
    contract: Mapping[str, Any],
    *,
    cgroup_limit_bytes: int,
    cgroup_current_bytes: int,
    host_effective_available_bytes: int,
    additional_request_bytes: int,
) -> None:
    execution = contract.get("execution")
    if not isinstance(execution, Mapping) or not isinstance(execution.get("resources"), Mapping):
        raise V29ContractError("V29 resource gate has no approved execution resources")
    resources = execution["resources"]
    cap = int(resources["task_memory_max_bytes"])
    reserve = int(resources["host_reserve_bytes"])
    if int(cgroup_limit_bytes) != cap:
        raise V29ContractError(f"V29 cgroup limit differs from contract: expected {cap}, got {cgroup_limit_bytes}")
    request = int(additional_request_bytes)
    if int(cgroup_current_bytes) + request > cap:
        raise V29ContractError(
            f"V29 cgroup admission refused: current {cgroup_current_bytes} + request {request} exceeds cap {cap}"
        )
    if int(host_effective_available_bytes) - request < reserve:
        raise V29ContractError(
            "V29 host admission refused: effective available "
            f"{host_effective_available_bytes} - request {request} is below reserve {reserve}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--launcher-values", action="store_true")
    parser.add_argument("--contract", required=True)
    parser.add_argument("--selector", required=True)
    args = parser.parse_args(argv)
    try:
        contract, contract_sha = require_authorized_contract(args.contract)
        selector, selector_sha = require_authorized_selector(
            args.selector,
            expected_sha256=None,
            contract_path=args.contract,
            contract_sha256=contract_sha,
            contract=contract,
        )
        execution = contract["execution"]
        if args.launcher_values:
            values = (
                str(execution["execution_root"]),
                str(execution["runtime_prefix"]),
                str(execution["abi_receipt_path"]),
                str(execution["jit_cache"]),
                str(execution["resources"]["task_memory_max_bytes"]),
                contract_sha,
                selector_sha,
            )
            sys.stdout.write("\n".join(values) + "\n")
        else:
            print(json.dumps({"status": "V29_AUTHORIZED", "contract_sha256": contract_sha, "selector_sha256": selector_sha}))
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"V29 launch refused: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
