"""Fail-closed, read-only reuse of one verified Gate-CD cache generation.

This is intentionally outside ``src`` so it cannot change the numerical-source
digest embedded in the existing exact tensor and carrier cache identities.
It is activated only by the reviewed Z10 recovery environment.
"""

from __future__ import annotations

import builtins
import hashlib
import json
import os
import shutil
import stat
import sys
from pathlib import Path
from typing import Any

MODE_ENV = "TASK40_EXACT_CACHE_REUSE_MODE"
CONTRACT_ENV = "TASK40_EXACT_CACHE_REUSE_CONTRACT"
CONTRACT_SHA_ENV = "TASK40_EXACT_CACHE_REUSE_CONTRACT_SHA256"
HOOK_ACTIVE_ENV = "TASK40_EXACT_CACHE_REUSE_HOOK_ACTIVE"
MODE = "verified_cache_only_v1"
SCHEMA = "task40.gate_cd.verified_cache_reuse.v1"
EXPECTED_PROFILE = "task40_gate_cd_fin0_sti_z10_m8n2_p6_direct_v1"
EXPECTED_RUN_ID = EXPECTED_PROFILE
EXPECTED_RAW_COUNT = 7288
EXPECTED_RAW_BYTES = 90713094656
EXPECTED_CARRIER_COUNT = 272
EXPECTED_CARRIER_BYTES = 1091188144
EXPECTED_JIT_FILE_COUNT = 32
EXPECTED_JIT_BYTES = 4660641154
Z10_PRELU_IDENTITY_COMPAT_SCHEMA = (
    "task40.gate_cd.z10_prelu_identity_snapshot_compatibility.v1"
)
Z10_P6_MODULE = "src.runners.p6_condensed_direct"
Z10_P6_FUNCTION = "run_p6_condensed_direct"
_Z10_IMPORT_GUARD_ATTRIBUTE = "_task40_z10_prelu_identity_import_guard"
_Z10_WRAPPED_FUNCTION_ATTRIBUTE = "_task40_z10_prelu_identity_wrapped"


class _Z10VerifiedIdentityPayload(dict):
    """Expose a pre-LU identity through ``get`` without changing payload bytes."""

    def __init__(self, payload: dict[str, Any], identity: dict[str, str]) -> None:
        super().__init__(payload)
        self._task40_verified_identity = identity

    def get(self, key: Any, default: Any = None) -> Any:
        if key == "identity":
            return self._task40_verified_identity
        return super().get(key, default)


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha256_file(path: Path) -> str:
    if path.is_symlink():
        raise ValueError(f"cache reuse evidence is symlinked: {path}")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError(f"cache reuse evidence is not a regular file: {path}")
        h = hashlib.sha256()
        with os.fdopen(fd, "rb", closefd=False) as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                h.update(block)
        return h.hexdigest()
    finally:
        os.close(fd)


def _read_regular_file(path: Path) -> bytes:
    if path.is_symlink():
        raise RuntimeError(f"Z10 identity snapshot is symlinked: {path}")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise RuntimeError(f"Z10 identity snapshot is not a regular file: {path}")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            return stream.read()
    finally:
        os.close(fd)


def _write_json_exclusive(path: Path, document: dict[str, Any]) -> None:
    raw = (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode()
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise RuntimeError(f"Z10 identity evidence is not a regular file: {path}")
        with os.fdopen(fd, "wb", closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(fd)


def _verified_z10_prelu_payload_identity(
    resolved_payload: dict[str, Any],
    output_directory: str | Path,
    source_sha: str | None,
    *,
    contract: dict[str, Any],
    environ: dict[str, str],
) -> dict[str, str]:
    """Derive legacy pre-LU identity fields from the validated run snapshots.

    This compatibility adapter is kept in ``scripts`` so the frozen numerical
    source digest remains unchanged. It runs at the worker's exact p6 adapter
    boundary, after the worker has validated the original resolved-config bytes.
    """
    if (
        contract.get("profile_identity") != EXPECTED_PROFILE
        or contract.get("run_id") != EXPECTED_RUN_ID
        or not isinstance(resolved_payload, dict)
        or resolved_payload.get("run_id") != EXPECTED_RUN_ID
        or "identity" in resolved_payload
        or not isinstance(source_sha, str)
        or len(source_sha) != 40
        or any(character not in "0123456789abcdef" for character in source_sha)
    ):
        raise RuntimeError("Z10 pre-LU compatibility adapter received a different run identity")

    attempt_id = contract.get("target_attempt_id")
    expected_attempt_id = environ.get("TASK40_GATE_CD_ATTEMPT_ID")
    expected_unit = environ.get("TASK40_GATE_CD_EXPECTED_UNIT")
    package_sha = environ.get("TASK40_GATE_CD_PACKAGE_SHA256")
    scope_path_value = environ.get("TASK40_GATE_CD_SCOPE_PATH")
    scope_sha = environ.get("TASK40_GATE_CD_SCOPE_SHA256")
    if (
        not isinstance(attempt_id, str)
        or expected_attempt_id != attempt_id
        or not isinstance(expected_unit, str)
        or not isinstance(package_sha, str)
        or len(package_sha) != 64
        or any(character not in "0123456789abcdef" for character in package_sha)
        or not isinstance(scope_path_value, str)
        or not Path(scope_path_value).is_absolute()
        or not isinstance(scope_sha, str)
        or len(scope_sha) != 64
        or any(character not in "0123456789abcdef" for character in scope_sha)
    ):
        raise RuntimeError("Z10 pre-LU compatibility adapter lacks its exact launch binding")
    attempt_suffix = attempt_id.rsplit("-", 1)[-1]
    expected_unit_for_attempt = (
        f"task40-gcd-z10-m8n2-{attempt_suffix}-{source_sha[:8]}.service"
    )
    if expected_unit != expected_unit_for_attempt:
        raise RuntimeError("Z10 pre-LU compatibility service unit differs from the exact launch")
    scope_path = Path(scope_path_value)
    if _sha256_file(scope_path) != scope_sha:
        raise RuntimeError("Z10 pre-LU compatibility scope hash changed")
    scope = json.loads(_read_regular_file(scope_path))
    if (
        scope.get("attempt_id") != attempt_id
        or scope.get("identity", {}).get("profile_identity") != EXPECTED_PROFILE
        or scope.get("identity", {}).get("run_id") != EXPECTED_RUN_ID
    ):
        raise RuntimeError("Z10 pre-LU compatibility scope differs from the exact attempt")

    from src.runners.exact_cache_contract import numerical_source_digest

    if numerical_source_digest() != contract.get("numerical_source_sha256"):
        raise RuntimeError("Z10 numerical source identity differs from the frozen cache")

    target_root, _, _ = _target_roots(contract, environ)
    if (
        Path(environ.get("TASK40_GATE_CD_ATTEMPT_CACHE_ROOT", "")).resolve()
        != Path(contract["target_attempt_cache_root"]).resolve()
        or Path(contract["target_attempt_cache_root"]).name
        != f"task40_gate_cd_formal_attempt_{attempt_id}"
    ):
        raise RuntimeError("Z10 pre-LU compatibility cache target differs from the attempt")

    requested_directory = Path(output_directory)
    if requested_directory.is_symlink():
        raise RuntimeError("Z10 pre-LU output directory is symlinked")
    run_directory = requested_directory.resolve(strict=True)
    snapshot_paths = {
        "manifest": run_directory / "run_manifest.json",
        "resolved": run_directory / "resolved_config.json",
        "input": run_directory / "input_original.dat",
        "input_sha": run_directory / "input_sha256.txt",
        "physical_sha": run_directory / "physical_model_sha256.txt",
        "source_sha": run_directory / "source_sha.txt",
    }
    snapshots = {name: _read_regular_file(path) for name, path in snapshot_paths.items()}
    manifest = json.loads(snapshots["manifest"])
    resolved = json.loads(snapshots["resolved"])
    provenance = resolved_payload.get("provenance")
    solver = resolved_payload.get("solver")
    if (
        not isinstance(provenance, dict)
        or not isinstance(solver, dict)
        or resolved != resolved_payload
        or resolved_payload.get("model_id")
        != "gate_cd_0p7nm_mapped_50x50_zminus10_to240"
        or solver.get("native_capacity_profile") != EXPECTED_PROFILE
    ):
        raise RuntimeError("Z10 pre-LU payload differs from the validated resolved snapshot")

    input_sha = hashlib.sha256(snapshots["input"]).hexdigest()
    resolved_sha = hashlib.sha256(snapshots["resolved"]).hexdigest()
    physical_sha = snapshots["physical_sha"].decode("ascii").strip()
    recorded_input_sha = snapshots["input_sha"].decode("ascii").strip()
    recorded_source_sha = snapshots["source_sha"].decode("ascii").strip()
    output_parent = Path(provenance.get("expected_output_parent", "")).resolve(strict=True)
    expected_manifest_values = {
        "run_id": EXPECTED_RUN_ID,
        "model_id": resolved_payload.get("model_id"),
        "source_sha": source_sha,
        "input_sha256": input_sha,
        "physical_model_sha256": physical_sha,
        "resolved_config_sha256": resolved_sha,
        "native_capacity_profile_identity": EXPECTED_PROFILE,
        "output_directory": str(run_directory),
    }
    if (
        output_parent != run_directory.parent
        or input_sha != recorded_input_sha
        or input_sha != provenance.get("input_sha256")
        or physical_sha != provenance.get("physical_model_sha256")
        or recorded_source_sha != source_sha
        or any(manifest.get(key) != value for key, value in expected_manifest_values.items())
    ):
        raise RuntimeError("Z10 pre-LU run manifest and immutable snapshots disagree")

    identity = {
        "input_sha256": input_sha,
        "physical_model_sha256": physical_sha,
        "resolved_config_sha256": resolved_sha,
    }
    evidence = {
        "schema": Z10_PRELU_IDENTITY_COMPAT_SCHEMA,
        "attempt_id": attempt_id,
        "profile_identity": EXPECTED_PROFILE,
        "run_id": EXPECTED_RUN_ID,
        "source_commit": source_sha,
        "service_unit": expected_unit,
        "package_sha256": package_sha,
        "scope_sha256": scope_sha,
        "output_directory": str(run_directory),
        "identity_source": "worker_validated_run_manifest_and_immutable_snapshots_v1",
        "numerical_source_sha256": contract.get("numerical_source_sha256"),
        "identity": identity,
    }
    _write_json_exclusive(run_directory / "z10_prelu_identity_compatibility.json", evidence)
    _append_audit(
        target_root,
        {
            "schema": SCHEMA,
            "event": "z10_prelu_identity_compatibility_applied",
            "pid": os.getpid(),
            "attempt_id": attempt_id,
            "output_directory": str(run_directory),
            "identity": identity,
            "source_commit": source_sha,
        },
    )
    return identity


def _install_z10_prelu_identity_adapter(
    contract: dict[str, Any], environ: dict[str, str]
) -> None:
    if contract.get("profile_identity") != EXPECTED_PROFILE:
        return
    if environ.get("TASK40_GATE_CD_SUBMISSION_MODE") != "runtime":
        return
    required_environment = (
        "TASK40_GATE_CD_ATTEMPT_ID",
        "TASK40_GATE_CD_EXPECTED_UNIT",
        "TASK40_GATE_CD_PACKAGE_SHA256",
        "TASK40_GATE_CD_SCOPE_PATH",
        "TASK40_GATE_CD_SCOPE_SHA256",
    )
    if any(not environ.get(name) for name in required_environment):
        raise RuntimeError("Z10 pre-LU identity adapter launch environment is incomplete")
    if environ.get("TASK40_GATE_CD_ATTEMPT_ID") != contract.get("target_attempt_id"):
        raise RuntimeError("Z10 pre-LU identity adapter attempt differs from its cache contract")
    from src.runners.exact_cache_contract import numerical_source_digest

    if numerical_source_digest() != contract.get("numerical_source_sha256"):
        raise RuntimeError("Z10 live numerical source differs from the frozen cache identity")
    if getattr(builtins, _Z10_IMPORT_GUARD_ATTRIBUTE, False):
        return

    original_import = builtins.__import__

    def import_with_z10_identity_adapter(
        name, globals=None, locals=None, fromlist=(), level=0
    ):
        try:
            module_result = original_import(name, globals, locals, fromlist, level)
        finally:
            if name == Z10_P6_MODULE:
                builtins.__import__ = original_import
        if name == Z10_P6_MODULE:
            module = sys.modules.get(Z10_P6_MODULE)
            original_function = getattr(module, Z10_P6_FUNCTION, None)
            if callable(original_function) and not getattr(
                original_function, _Z10_WRAPPED_FUNCTION_ATTRIBUTE, False
            ):
                def run_with_verified_identity(
                    payload, output_directory, *args, **kwargs
                ):
                    if isinstance(payload, dict) and payload.get("run_id") == EXPECTED_RUN_ID:
                        source_sha = kwargs.get("source_sha")
                        if source_sha is None and args:
                            source_sha = args[0]
                        identity = _verified_z10_prelu_payload_identity(
                            payload,
                            output_directory,
                            source_sha,
                            contract=contract,
                            environ=environ,
                        )
                        enriched_payload = dict(payload)
                        existing_identity = enriched_payload.get("identity")
                        if existing_identity is not None and existing_identity != identity:
                            raise RuntimeError("Z10 pre-LU payload identity overlay conflicts")
                        payload = _Z10VerifiedIdentityPayload(payload, identity)
                    return original_function(payload, output_directory, *args, **kwargs)

                setattr(run_with_verified_identity, _Z10_WRAPPED_FUNCTION_ATTRIBUTE, True)
                setattr(module, Z10_P6_FUNCTION, run_with_verified_identity)
        return module_result

    setattr(import_with_z10_identity_adapter, _Z10_WRAPPED_FUNCTION_ATTRIBUTE, True)
    builtins.__import__ = import_with_z10_identity_adapter
    setattr(builtins, _Z10_IMPORT_GUARD_ATTRIBUTE, True)


def _read_bound_contract(environ: dict[str, str]) -> dict[str, Any]:
    contract_value = environ.get(CONTRACT_ENV)
    supplied_sha = environ.get(CONTRACT_SHA_ENV)
    if not contract_value or not supplied_sha:
        raise RuntimeError("verified cache reuse contract path/SHA is missing")
    contract_path = Path(contract_value)
    if not contract_path.is_absolute() or contract_path.is_symlink():
        raise RuntimeError("verified cache reuse contract path is not absolute and regular")
    raw = contract_path.read_bytes()
    if _sha256_bytes(raw) != supplied_sha:
        raise RuntimeError("verified cache reuse contract SHA256 mismatch")
    try:
        contract = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("verified cache reuse contract JSON is malformed") from exc
    if not isinstance(contract, dict) or contract.get("schema") != SCHEMA:
        raise RuntimeError("verified cache reuse contract schema is unsupported")
    if (
        contract.get("profile_identity") != EXPECTED_PROFILE
        or contract.get("run_id") != EXPECTED_RUN_ID
        or contract.get("raw_tensor_count") != EXPECTED_RAW_COUNT
        or contract.get("raw_tensor_payload_bytes") != EXPECTED_RAW_BYTES
        or contract.get("carrier_count") != EXPECTED_CARRIER_COUNT
        or contract.get("carrier_payload_bytes") != EXPECTED_CARRIER_BYTES
        or contract.get("require_cache_hits_only") is not True
        or contract.get("allow_compute_on_miss") is not False
        or contract.get("allow_source_cache_writes") is not False
    ):
        raise RuntimeError("verified cache reuse contract differs from the frozen Z10 case")

    source_root = Path(contract.get("source_attempt_cache_root", ""))
    source_jit_root = Path(contract.get("source_jit_cache_root", ""))
    tensor_root = Path(contract.get("source_tensor_root", ""))
    carrier_root = Path(contract.get("source_carrier_root", ""))
    carrier_checkpoint_root = Path(contract.get("source_carrier_checkpoint_root", ""))
    if (
        not source_root.is_absolute()
        or source_root.is_symlink()
        or not source_jit_root.is_absolute()
        or source_jit_root.is_symlink()
        or not source_jit_root.is_dir()
        or tensor_root != source_root / "tensor"
        or carrier_root != source_root / "carrier"
        or not tensor_root.is_dir()
        or tensor_root.is_symlink()
        or not carrier_root.is_dir()
        or carrier_root.is_symlink()
        or not carrier_checkpoint_root.is_absolute()
        or carrier_checkpoint_root.is_symlink()
        or not carrier_checkpoint_root.is_dir()
        or carrier_checkpoint_root.parent.parent != carrier_root
        or len(carrier_checkpoint_root.name) != 64
        or any(c not in "0123456789abcdef" for c in carrier_checkpoint_root.name)
    ):
        raise RuntimeError("verified source cache roots are missing, unsafe, or inconsistent")
    target_root = Path(contract.get("target_attempt_cache_root", ""))
    target_attempt_id = contract.get("target_attempt_id")
    if (
        not isinstance(target_attempt_id, str)
        or not target_attempt_id
        or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in target_attempt_id)
        or not target_root.is_absolute()
        or target_root.name != f"task40_gate_cd_formal_attempt_{target_attempt_id}"
        or target_root == source_root
    ):
        raise RuntimeError("target cache root is not bound to a distinct recovery attempt")

    raw_report_path = Path(contract.get("raw_integrity_report_path", ""))
    carrier_report_path = Path(contract.get("carrier_integrity_report_path", ""))
    jit_report_path = Path(contract.get("jit_integrity_report_path", ""))
    if (
        not raw_report_path.is_absolute()
        or not carrier_report_path.is_absolute()
        or not jit_report_path.is_absolute()
        or _sha256_file(raw_report_path) != contract.get("raw_integrity_report_sha256")
        or _sha256_file(carrier_report_path)
        != contract.get("carrier_integrity_report_sha256")
        or _sha256_file(jit_report_path) != contract.get("jit_integrity_report_sha256")
    ):
        raise RuntimeError("verified cache integrity report hash mismatch")
    raw_report = json.loads(raw_report_path.read_text(encoding="utf-8"))
    carrier_report = json.loads(carrier_report_path.read_text(encoding="utf-8"))
    jit_report = json.loads(jit_report_path.read_text(encoding="utf-8"))
    module_hashes = raw_report.get("modules")
    if (
        raw_report.get("status") != "PASS"
        or raw_report.get("root") != str(tensor_root)
        or raw_report.get("requests") != EXPECTED_RAW_COUNT
        or raw_report.get("verified") != EXPECTED_RAW_COUNT
        or raw_report.get("payload_bytes") != EXPECTED_RAW_BYTES
        or raw_report.get("errors") != []
        or not isinstance(raw_report.get("rows"), list)
        or len(raw_report["rows"]) != EXPECTED_RAW_COUNT
        or not isinstance(module_hashes, dict)
        or len(module_hashes) != 1
        or set(module_hashes.values()) != {contract.get("raw_tensor_module_sha256")}
        or carrier_report.get("status") != "PASS"
        or carrier_report.get("root") != str(carrier_checkpoint_root)
        or carrier_report.get("verified") != EXPECTED_CARRIER_COUNT
        or carrier_report.get("bytes") != EXPECTED_CARRIER_BYTES
        or carrier_report.get("errors") != []
        or not isinstance(carrier_report.get("rows"), list)
        or len(carrier_report["rows"]) != EXPECTED_CARRIER_COUNT
        or [item.get("index") for item in carrier_report["rows"]]
        != list(range(EXPECTED_CARRIER_COUNT))
        or jit_report.get("schema") != "task40.gate_cd.jit_cache_integrity.v1"
        or jit_report.get("root") != str(source_jit_root)
        or jit_report.get("file_count") != EXPECTED_JIT_FILE_COUNT
        or jit_report.get("payload_bytes") != EXPECTED_JIT_BYTES
        or jit_report.get("errors") != []
        or not isinstance(jit_report.get("files"), list)
        or len(jit_report["files"]) != EXPECTED_JIT_FILE_COUNT
    ):
        raise RuntimeError("independent cache/JIT integrity reports do not prove the frozen counts")
    jit_files = jit_report["files"]
    jit_names = [item.get("name") for item in jit_files]
    if (
        len(set(jit_names)) != EXPECTED_JIT_FILE_COUNT
        or any(
            not isinstance(item.get("name"), str)
            or Path(item["name"]).name != item["name"]
            or type(item.get("bytes")) is not int
            or item["bytes"] < 0
            or not isinstance(item.get("sha256"), str)
            or len(item["sha256"]) != 64
            or any(c not in "0123456789abcdef" for c in item["sha256"])
            for item in jit_files
        )
        or sum(item["bytes"] for item in jit_files) != EXPECTED_JIT_BYTES
        or not any(
            item["sha256"] == contract.get("raw_tensor_module_sha256")
            and item["name"].endswith(".cpython-312-x86_64-linux-gnu.so")
            for item in jit_files
        )
    ):
        raise RuntimeError("verified JIT file inventory is malformed or incomplete")
    return contract


def _directory(path: Path, *, label: str) -> Path:
    if not path.is_absolute() or path.is_symlink() or not path.is_dir():
        raise RuntimeError(f"{label} is missing, non-absolute, or symlinked: {path}")
    return path.resolve(strict=True)


def _target_roots(contract: dict[str, Any], environ: dict[str, str]) -> tuple[Path, Path, Path]:
    supplied = environ.get("TASK40_GATE_CD_ATTEMPT_CACHE_ROOT")
    if not supplied:
        raise RuntimeError("Gate-CD runtime attempt cache root is missing")
    target_root = Path(supplied)
    if not target_root.is_absolute() or target_root.is_symlink():
        raise RuntimeError("Gate-CD runtime attempt cache root is unsafe")
    target_root = target_root.resolve(strict=True)
    if target_root != Path(contract["target_attempt_cache_root"]).resolve():
        raise RuntimeError("runtime Gate-CD attempt root differs from the cache reuse contract")
    tensor_target = _directory(target_root / "tensor", label="target tensor cache")
    carrier_target = _directory(target_root / "carrier", label="target carrier cache")
    source_root = Path(contract["source_attempt_cache_root"]).resolve(strict=True)
    if target_root == source_root:
        raise RuntimeError("target and verified source cache roots must be distinct")
    return target_root, tensor_target, carrier_target


def _append_audit(target_root: Path, event: dict[str, Any]) -> None:
    path = target_root / "verified_cache_reuse.jsonl"
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise RuntimeError("cache reuse audit path is not a regular file")
        raw = (json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n").encode()
        os.write(fd, raw)
        os.fsync(fd)
    finally:
        os.close(fd)


def _materialize_jit_cache(
    *, contract: dict[str, Any], attempt_cache: dict[str, Path], environ: dict[str, str]
) -> None:
    target_root, _, _ = _target_roots(contract, environ)
    expected_target = Path(contract["target_attempt_cache_root"]).resolve()
    if target_root != expected_target:
        raise RuntimeError("runtime Gate-CD attempt differs from the reviewed cache-reuse target")
    source = _directory(
        Path(contract["source_jit_cache_root"]), label="verified source FFCx JIT cache"
    )
    xdg = _directory(Path(attempt_cache["xdg"]), label="new attempt XDG cache")
    if xdg.parent.resolve(strict=True) != target_root:
        raise RuntimeError("new attempt XDG path escaped its target cache root")
    target = xdg / "fenics"
    if target.exists() or target.is_symlink():
        raise RuntimeError("new attempt FFCx JIT cache must be empty before materialization")
    report_path = Path(contract["jit_integrity_report_path"])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    expected = {item["name"]: item for item in report["files"]}
    source_entries = sorted(source.iterdir(), key=lambda item: item.name)
    if (
        len(source_entries) != EXPECTED_JIT_FILE_COUNT
        or {item.name for item in source_entries} != set(expected)
        or any(item.is_symlink() or not item.is_file() for item in source_entries)
    ):
        raise RuntimeError("source FFCx JIT cache no longer matches its reviewed file inventory")
    target.mkdir(mode=0o700)
    total_bytes = 0
    try:
        for source_file in source_entries:
            record = expected[source_file.name]
            before = _stat_identity(source_file)
            if before[2] != record["bytes"]:
                raise RuntimeError(f"source FFCx cache size changed: {source_file.name}")
            target_file = target / source_file.name
            digest = hashlib.sha256()
            copied = 0
            source_fd = os.open(source_file, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            target_fd = os.open(
                target_file,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            try:
                with (
                    os.fdopen(source_fd, "rb", closefd=False) as source_stream,
                    os.fdopen(target_fd, "wb", closefd=False) as target_stream,
                ):
                    for block in iter(lambda: source_stream.read(4 * 1024 * 1024), b""):
                        digest.update(block)
                        target_stream.write(block)
                        copied += len(block)
                    target_stream.flush()
                if _stat_identity(source_file) != before:
                    raise RuntimeError(f"source FFCx cache changed while copying: {source_file.name}")
            finally:
                os.close(source_fd)
                os.close(target_fd)
            if copied != record["bytes"] or digest.hexdigest() != record["sha256"]:
                raise RuntimeError(f"source FFCx cache SHA256 mismatch: {source_file.name}")
            mode = int(record.get("mode", 0o400)) & ~0o222
            if mode & 0o444 == 0:
                mode |= 0o400
            os.chmod(target_file, mode)
            total_bytes += copied
        if total_bytes != EXPECTED_JIT_BYTES:
            raise RuntimeError("materialized FFCx cache byte count differs from its contract")
        if {item.name for item in target.iterdir()} != set(expected):
            raise RuntimeError("materialized FFCx cache file set differs from its contract")
        _append_audit(
            target_root,
            {
                "schema": SCHEMA,
                "event": "jit_cache_materialized_read_only",
                "source_jit_cache_root": str(source),
                "target_jit_cache_root": str(target),
                "file_count": EXPECTED_JIT_FILE_COUNT,
                "payload_bytes": total_bytes,
                "raw_tensor_compute_on_cache_miss": False,
                "new_distinct_jit_modules_allowed_in_attempt_cache": True,
            },
        )
    except BaseException:
        try:
            os.chmod(target, 0o700)
            shutil.rmtree(target)
        except OSError:
            pass
        raise


def _stat_identity(path: Path) -> tuple[int, int, int, int, int]:
    if path.is_symlink():
        raise RuntimeError(f"verified cache shard path is symlinked: {path}")
    info = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode):
        raise RuntimeError(f"verified cache shard payload is not regular: {path}")
    return (
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def install(
    *,
    parallel_cache: Any | None = None,
    carrier_module: Any | None = None,
    lease_class: Any | None = None,
    environ: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    """Install the one-attempt cache-only guard; return ``None`` when disabled."""
    env = os.environ if environ is None else environ
    related = (CONTRACT_ENV, CONTRACT_SHA_ENV)
    mode = env.get(MODE_ENV)
    if mode is None:
        if any(env.get(name) for name in related):
            raise RuntimeError("cache reuse contract supplied without its explicit mode")
        return None
    if mode != MODE:
        raise RuntimeError(f"unsupported exact cache reuse mode: {mode!r}")
    contract = _read_bound_contract(env)
    _install_z10_prelu_identity_adapter(contract, env)
    if parallel_cache is None:
        from src.solvers import parallel_tensor_cache as parallel_cache
    if carrier_module is None:
        from src.solvers import carrier_checkpoint as carrier_module

    original_load_shard = parallel_cache.load_shard
    original_digest = parallel_cache.digest
    original_key_for = parallel_cache.key_for
    original_carrier_init = carrier_module.CarrierCheckpoint.__init__
    original_carrier_load = carrier_module.CarrierCheckpoint.load
    original_restore_prefix = carrier_module.CarrierCheckpoint.restore_prefix
    memo: dict[str, tuple[dict[str, Any], tuple[int, int, int, int, int]]] = {}

    def load_shard(root: str | Path, job: dict[str, Any]):
        _, tensor_target, _ = _target_roots(contract, env)
        supplied_root = Path(root)
        if supplied_root.is_symlink() or supplied_root.resolve(strict=True) != tensor_target:
            raise RuntimeError("raw tensor loader requested an unreviewed cache root")
        source = Path(contract["source_tensor_root"]).resolve(strict=True)
        key = original_key_for(job)
        cached = memo.get(key)
        if cached is None:
            folder = source / key
            marker = folder / "complete.json"
            payload = folder / "tensor.npy"
            if folder.is_symlink() or marker.is_symlink() or payload.is_symlink():
                raise RuntimeError("verified raw tensor shard contains a symlink")
            before = _stat_identity(payload)
            entry = original_load_shard(source, job)
            after = _stat_identity(payload)
            if entry is None:
                raise RuntimeError(f"verified raw tensor cache miss for key {key}")
            if before != after:
                raise RuntimeError(f"verified raw tensor shard changed during read: {key}")
            cached = (entry, after)
            memo[key] = cached
        else:
            payload = Path(cached[0]["path"])
            if _stat_identity(payload) != cached[1]:
                raise RuntimeError(f"verified raw tensor shard changed after preflight: {key}")
        return cached[0]

    def run_batch(
        jobs,
        root,
        cpus,
        *,
        timeout=None,
        progress=None,
        available_floor=68_719_476_736,
        disk_reserve=10_737_418_240,
    ):
        target_root, tensor_target, _ = _target_roots(contract, env)
        job_rows = list(jobs)
        keys = [original_key_for(job) for job in job_rows]
        if (
            Path(root).resolve(strict=True) != tensor_target
            or len(job_rows) != EXPECTED_RAW_COUNT
            or len(set(keys)) != EXPECTED_RAW_COUNT
            or not cpus
            or len(set(map(int, cpus))) != len(cpus)
        ):
            raise RuntimeError("runtime raw tensor job set differs from the verified Z10 contract")
        expected_module_sha = contract["raw_tensor_module_sha256"]
        verified: dict[str, dict[str, Any]] = {}
        module_identities: dict[str, tuple[tuple[int, int, int, int, int], str]] = {}
        for key, job in zip(keys, job_rows, strict=True):
            if job.get("module_sha256") != expected_module_sha:
                raise RuntimeError("runtime raw tensor module identity differs from the cache report")
            module_path = Path(job.get("module_path", ""))
            if module_path.is_symlink():
                raise RuntimeError("runtime compiled tensor module is symlinked")
            resolved_module = module_path.resolve(strict=True)
            module_identity = _stat_identity(resolved_module)
            module_record = module_identities.get(str(resolved_module))
            if module_record is None:
                module_sha = original_digest(resolved_module)
                if _stat_identity(resolved_module) != module_identity:
                    raise RuntimeError("runtime compiled tensor module changed during hashing")
                module_record = (module_identity, module_sha)
                module_identities[str(resolved_module)] = module_record
            elif _stat_identity(resolved_module) != module_record[0]:
                raise RuntimeError("runtime compiled tensor module changed after hashing")
            if module_record[1] != expected_module_sha:
                raise RuntimeError("runtime compiled tensor module differs from cache report")
            hit = load_shard(tensor_target, job)
            if hit is None or hit.get("key") != key:
                raise RuntimeError(f"verified raw tensor cache miss for key {key}")
            verified[key] = {"key": key, "cache_hit": True}
            if progress is not None:
                progress(len(verified), len(job_rows), verified[key])
        if len(verified) != EXPECTED_RAW_COUNT:
            raise RuntimeError("verified raw tensor cache did not cover every requested class")
        ordered_keys = sorted(verified)
        _append_audit(
            target_root,
            {
                "schema": SCHEMA,
                "event": "raw_tensor_cache_preflight_complete",
                "source_tensor_root": contract["source_tensor_root"],
                "target_tensor_root": str(tensor_target),
                "requested": len(job_rows),
                "cache_hits": len(verified),
                "cache_misses": 0,
                "computed": 0,
                "unique_key_sha256": _sha256_bytes(("\n".join(ordered_keys) + "\n").encode()),
                "compiled_module_sha256": expected_module_sha,
                "source_cache_writes_allowed": False,
            },
        )
        return {key: verified[key] for key in ordered_keys}

    def blocked_compute_one(*args, **kwargs):
        raise RuntimeError("verified cache-only mode forbids raw tensor computation")

    def blocked_commit_shard(*args, **kwargs):
        raise RuntimeError("verified cache-only mode forbids raw tensor cache writes")

    parallel_cache.load_shard = load_shard
    parallel_cache.run_batch = run_batch
    parallel_cache.compute_one = blocked_compute_one
    parallel_cache.commit_shard = blocked_commit_shard

    checkpoint_type = carrier_module.CarrierCheckpoint

    def carrier_init(self, root, context, **kwargs):
        _, _, carrier_target = _target_roots(contract, env)
        requested = Path(root)
        if requested.is_symlink() or requested.resolve(strict=True) != carrier_target:
            raise RuntimeError("carrier loader requested an unreviewed cache root")
        if context.get("numerical_source_sha256") != contract.get("numerical_source_sha256"):
            raise RuntimeError("live carrier numerical source identity differs from cache contract")
        context_sha = _sha256_bytes(
            json.dumps(
                context,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode()
        )
        if context_sha != Path(contract["source_carrier_checkpoint_root"]).name:
            raise RuntimeError("live carrier context hash differs from the verified checkpoint")
        original_carrier_init(
            self,
            contract["source_carrier_root"],
            context,
            **kwargs,
        )
        expected_root = Path(contract["source_carrier_checkpoint_root"]).resolve(strict=True)
        if self.root.resolve(strict=True) != expected_root:
            raise RuntimeError("live carrier context differs from the verified checkpoint identity")

    def carrier_load(self, index, mode):
        expected_root = Path(contract["source_carrier_checkpoint_root"]).resolve(strict=True)
        if self.root.resolve(strict=True) != expected_root:
            raise RuntimeError("carrier checkpoint root drifted after initialization")
        if not 0 <= int(index) < EXPECTED_CARRIER_COUNT:
            raise RuntimeError("carrier checkpoint index lies outside the verified mode set")
        folder = self.root / str(index)
        marker = folder / "complete.json"
        payload = folder / "arrays.npz"
        if folder.is_symlink() or marker.is_symlink() or payload.is_symlink():
            raise RuntimeError("verified carrier checkpoint contains a symlink")
        result = original_carrier_load(self, index, mode)
        if result is None:
            raise RuntimeError(f"verified carrier checkpoint miss at mode {index}")
        return result

    def restore_prefix(self, modes):
        mode_rows = list(modes)
        if len(mode_rows) != EXPECTED_CARRIER_COUNT:
            raise RuntimeError("runtime carrier inventory differs from the verified 272-mode cache")
        restored = original_restore_prefix(self, mode_rows)
        if len(restored) != EXPECTED_CARRIER_COUNT:
            raise RuntimeError("verified carrier checkpoint did not restore every signed mode")
        _append_audit(
            _target_roots(contract, env)[0],
            {
                "schema": SCHEMA,
                "event": "carrier_checkpoint_restore_complete",
                "source_carrier_checkpoint_root": contract["source_carrier_checkpoint_root"],
                "restored_modes": len(restored),
                "cache_misses": 0,
                "computed": 0,
                "source_cache_writes_allowed": False,
            },
        )
        return restored

    def blocked_carrier_commit(self, *args, **kwargs):
        raise RuntimeError("verified cache-only mode forbids carrier checkpoint writes")

    checkpoint_type.__init__ = carrier_init
    checkpoint_type.load = carrier_load
    checkpoint_type.restore_prefix = restore_prefix
    checkpoint_type.commit = blocked_carrier_commit

    if lease_class is None:
        from src.runners.task40_gate_cd_formal_admission import GateCDRuntimeLease

        lease_class = GateCDRuntimeLease
    original_prepare_attempt_cache = lease_class.prepare_attempt_cache

    def prepare_attempt_cache(self):
        profile = self.scope.get("identity", {}).get("profile_identity")
        run_id = self.scope.get("identity", {}).get("run_id")
        attempt_id = self.scope.get("attempt_id")
        expected_root = Path(contract["target_attempt_cache_root"])
        if (
            profile != EXPECTED_PROFILE
            or run_id != EXPECTED_RUN_ID
            or attempt_id != contract["target_attempt_id"]
            or self.submission_mode != "runtime"
            or Path(self.cache_root).resolve() != expected_root
        ):
            raise RuntimeError("attempt cache lease differs from the verified recovery contract")
        attempt_cache = original_prepare_attempt_cache(self)
        _materialize_jit_cache(
            contract=contract,
            attempt_cache=attempt_cache,
            environ=env,
        )
        return attempt_cache

    lease_class.prepare_attempt_cache = prepare_attempt_cache
    env[HOOK_ACTIVE_ENV] = "1"
    supplied_target = env.get("TASK40_GATE_CD_ATTEMPT_CACHE_ROOT")
    if supplied_target:
        target_path = Path(supplied_target)
        if target_path.exists():
            target_root, _, _ = _target_roots(contract, env)
            _append_audit(
                target_root,
                {
                    "schema": SCHEMA,
                    "event": "python_startup_guard_installed",
                    "pid": os.getpid(),
                    "contract_sha256": env.get(CONTRACT_SHA_ENV),
                    "attempt_cache_root": str(target_root),
                    "python_executable": os.path.realpath(os.sys.executable),
                },
            )
    return contract


def install_from_environment() -> dict[str, Any] | None:
    return install()
