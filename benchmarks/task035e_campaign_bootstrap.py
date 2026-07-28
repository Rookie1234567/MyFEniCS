#!/usr/bin/env python3
"""Create the immutable no-PDE inputs for one formal Task035e campaign.

This entrypoint closes the gap between the two initial-space producers and the
repository-owned campaign handler.  It accepts only a new private child of the
ignored ``benchmarks/artifacts/task035e`` root and one already verified clean
source SHA.  Path A/B, MPI width, cycle count, solver configuration, runtime
layout, and the suggested handler argv are fixed here rather than assembled
by an ad-hoc shell script.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
from typing import Any, Mapping, Sequence

from benchmarks import task035e_trial_metadata as trial_metadata
from benchmarks.task035e_blind_campaign import (
    CAMPAIGN_SCHEMA,
    MAXIMUM_CYCLES,
    BlindCampaignIdentity,
    BlindPathIdentity,
    initialize_campaign,
)
from benchmarks.task035e_campaign_handlers import (
    live_qualified_abi_sha256,
)
from benchmarks.task035e_initial_space import write_initial_space_bundle


ROOT = Path(__file__).resolve().parents[1]
FORMAL_ARTIFACT_ROOT = (
    ROOT / "benchmarks" / "artifacts" / "task035e"
)
BOOTSTRAP_SCHEMA = "task035e.formal-campaign-bootstrap.v1"
BOOTSTRAP_RECEIPT_SCHEMA = (
    "task035e.formal-campaign-bootstrap-write-receipt.v1"
)
HANDLER_MODULE = "benchmarks.task035e_campaign_handlers"
FORMAL_MPI_SIZE = 8
DEFAULT_TIMEOUT_SECONDS = 43200.0
MANIFEST_NAME = "bootstrap-manifest.json"

_SOURCE_SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_PROTECTED_PATH_PARTS = frozenset(
    {
        "ref" + "erence_certifier",
        "hid" + "den_auditor",
        "sealed_" + "reference",
        "sealed-" + "reference",
        "golden_" + "reference",
        "golden-" + "reference",
    }
)
_ROOT_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "pass",
        "source_sha",
        "source_probe_sha256",
        "abi_sha256",
        "formal_mpi_size",
        "maximum_cycles",
        "paths",
        "runtime",
        "handler",
        "source_clean_verified",
        "source_stable_during_bootstrap",
        "abi_stable_during_bootstrap",
        "protected_inputs_consumed",
        "pde_executed",
        "ordinary_default_changed",
        "manifest_payload_sha256",
    }
)
_PATH_KEYS = frozenset(
    {
        "path_id",
        "trial_id",
        "nominal_h_nm",
        "initial_plan_path",
        "initial_plan_sha256",
        "initial_space_authority_path",
        "initial_space_authority_sha256",
        "qualified_solver_config_path",
        "qualified_solver_config_sha256",
    }
)
_RUNTIME_KEYS = frozenset(
    {
        "output_root",
        "campaign_root",
        "campaign_identity_path",
        "campaign_identity_sha256",
        "artifact_root",
        "tensor_cache_directory",
        "python_executable",
        "timeout_seconds",
    }
)
_HANDLER_KEYS = frozenset(
    {
        "module",
        "argv",
        "argv_sha256",
    }
)
_SOURCE_STATE_KEYS = frozenset(
    {
        "repo_root",
        "head_sha",
        "status_lines",
    }
)


class CampaignBootstrapError(ValueError):
    """Raised when formal campaign inputs cannot be created fail-closed."""


@dataclass(frozen=True, slots=True)
class CampaignBootstrapReceipt:
    """Identity of one immutable campaign bootstrap manifest."""

    manifest_path: Path
    manifest_file_sha256: str
    manifest_payload_sha256: str
    source_sha: str
    abi_sha256: str
    handler_argv: tuple[str, ...]


def _reject_nonfinite(value: str) -> None:
    raise CampaignBootstrapError(
        f"non-finite JSON constant is forbidden: {value}"
    )


def _reject_duplicate_object(
    pairs: Sequence[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CampaignBootstrapError(
                f"duplicate JSON object key is forbidden: {key}"
            )
        result[key] = value
    return result


def _canonical(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _canonical(item)
            for key, item in sorted(
                value.items(),
                key=lambda pair: str(pair[0]),
            )
        }
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    return value


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            _canonical(value),
            sort_keys=True,
            indent=2,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("ascii")


def _json_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            _canonical(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    ).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _source_sha(value: Any) -> str:
    source = str(value)
    if _SOURCE_SHA_RE.fullmatch(source) is None:
        raise CampaignBootstrapError(
            "verified_clean_source_sha must be one lowercase full Git SHA"
        )
    return source


def _sha256(value: Any, *, label: str) -> str:
    digest = str(value)
    if _SHA256_RE.fullmatch(digest) is None:
        raise CampaignBootstrapError(
            f"{label} must be one lowercase SHA-256"
        )
    return digest


def _exact(
    value: Any,
    keys: frozenset[str],
    *,
    label: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CampaignBootstrapError(f"{label} must be one JSON object")
    if set(value) != set(keys):
        raise CampaignBootstrapError(
            f"{label} does not use its closed schema; "
            f"missing={sorted(set(keys) - set(value))}, "
            f"extra={sorted(set(value) - set(keys))}"
        )
    return value


def _absolute_linux_path(
    path: Path,
    *,
    label: str,
    allow_final_symlink: bool = False,
) -> Path:
    raw = Path(path).expanduser()
    if not raw.is_absolute():
        raise CampaignBootstrapError(f"{label} must be absolute")
    rendered = raw.as_posix()
    if rendered == "/mnt" or rendered.startswith("/mnt/"):
        raise CampaignBootstrapError(
            f"{label} must use the WSL Linux filesystem"
        )
    cursor = Path(raw.anchor)
    path_parts = raw.parts[1:]
    for index, part in enumerate(path_parts):
        cursor /= part
        if cursor.is_symlink() and not (
            allow_final_symlink and index == len(path_parts) - 1
        ):
            raise CampaignBootstrapError(
                f"{label} must not cross a symlink"
            )
        if not cursor.exists():
            break
    resolved = raw.resolve()
    if {part.lower() for part in resolved.parts}.intersection(
        _PROTECTED_PATH_PARTS
    ):
        raise CampaignBootstrapError(
            f"{label} crosses a protected evaluator layer"
        )
    return resolved


def _new_output_root(path: Path) -> Path:
    raw = Path(path).expanduser()
    if raw.exists() or raw.is_symlink():
        raise FileExistsError(
            f"refusing to overwrite campaign bootstrap root: {raw}"
        )
    resolved = _absolute_linux_path(raw, label="output root")
    formal_root = FORMAL_ARTIFACT_ROOT.resolve()
    if resolved.parent != formal_root:
        raise CampaignBootstrapError(
            "output root must be one new direct child of the ignored "
            "benchmarks/artifacts/task035e root"
        )
    if not _git_path_is_ignored(resolved):
        raise CampaignBootstrapError(
            "formal campaign bootstrap output is not Git-ignored"
        )
    parent = formal_root.parent
    if not parent.is_dir():
        raise CampaignBootstrapError(
            "benchmarks/artifacts must already be one directory"
        )
    if formal_root.exists() or formal_root.is_symlink():
        _private_directory(
            formal_root,
            label="Task035e formal artifact root",
        )
    else:
        previous_umask = os.umask(0o077)
        try:
            os.mkdir(formal_root, mode=0o700)
        finally:
            os.umask(previous_umask)
        _private_directory(
            formal_root,
            label="Task035e formal artifact root",
        )
    previous_umask = os.umask(0o077)
    try:
        os.mkdir(resolved, mode=0o700)
    finally:
        os.umask(previous_umask)
    return _private_directory(resolved, label="output root")


def _git_path_is_ignored(path: Path) -> bool:
    """Prove a prospective formal artifact path is covered by .gitignore."""

    completed = subprocess.run(
        ("git", "check-ignore", "--quiet", "--", str(path)),
        cwd=ROOT,
        env={
            **os.environ,
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
        },
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if completed.returncode == 0:
        return True
    if completed.returncode == 1:
        return False
    detail = completed.stderr.strip()
    raise CampaignBootstrapError(
        "read-only Git ignore probe failed"
        + (f": {detail}" if detail else "")
    )


def _validated_formal_output_root(path: Path) -> Path:
    resolved = _private_directory(path, label="bootstrap output root")
    if (
        resolved.parent != FORMAL_ARTIFACT_ROOT.resolve()
        or not _git_path_is_ignored(resolved)
    ):
        raise CampaignBootstrapError(
            "bootstrap output root is outside the ignored formal artifact "
            "scope"
        )
    return resolved


def _private_directory(path: Path, *, label: str) -> Path:
    resolved = _absolute_linux_path(path, label=label)
    try:
        metadata = resolved.stat()
    except OSError as exc:
        raise CampaignBootstrapError(f"{label} is absent") from exc
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise CampaignBootstrapError(
            f"{label} must be one mode-0700 directory"
        )
    return resolved


def _make_private_directory(parent: Path, name: str) -> Path:
    destination = parent / name
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(
            f"refusing to reuse bootstrap directory: {destination}"
        )
    previous_umask = os.umask(0o077)
    try:
        os.mkdir(destination, mode=0o700)
    finally:
        os.umask(previous_umask)
    return _private_directory(destination, label=f"{name} directory")


def _private_file(
    path: Path,
    *,
    label: str,
    expected_sha256: str | None = None,
) -> Path:
    resolved = _absolute_linux_path(path, label=label)
    try:
        metadata = resolved.stat()
    except OSError as exc:
        raise CampaignBootstrapError(f"{label} is absent") from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        raise CampaignBootstrapError(
            f"{label} must be one mode-0600 regular file"
        )
    if (
        expected_sha256 is not None
        and _file_sha256(resolved)
        != _sha256(expected_sha256, label=f"{label} SHA-256")
    ):
        raise CampaignBootstrapError(f"{label} SHA-256 differs")
    return resolved


def _atomic_private_json(
    path: Path,
    payload: Mapping[str, Any],
) -> str:
    if path.exists() or path.is_symlink():
        raise FileExistsError(
            f"refusing to overwrite immutable bootstrap manifest: {path}"
        )
    parent = _private_directory(
        path.parent,
        label="bootstrap manifest directory",
    )
    body = _canonical_bytes(payload)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
        temporary.unlink()
        directory_descriptor = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary.unlink(missing_ok=True)
        raise
    return hashlib.sha256(body).hexdigest()


def _git_source_state() -> Mapping[str, Any]:
    environment = dict(os.environ)
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    environment["GIT_TERMINAL_PROMPT"] = "0"

    def run(*arguments: str) -> str:
        completed = subprocess.run(
            ("git", *arguments),
            cwd=ROOT,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise CampaignBootstrapError(
                "read-only Git source probe failed"
                + (f": {detail}" if detail else "")
            )
        return completed.stdout

    return {
        "repo_root": run("rev-parse", "--show-toplevel").strip(),
        "head_sha": run("rev-parse", "HEAD").strip(),
        "status_lines": tuple(
            line
            for line in run(
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            ).splitlines()
            if line
        ),
    }


def _validated_source_state(
    payload: Mapping[str, Any],
    *,
    expected_source_sha: str,
    label: str,
) -> Mapping[str, Any]:
    row = _exact(payload, _SOURCE_STATE_KEYS, label=label)
    status = row["status_lines"]
    if (
        Path(str(row["repo_root"])).resolve() != ROOT.resolve()
        or row["head_sha"] != expected_source_sha
        or not isinstance(status, (list, tuple))
        or any(not isinstance(item, str) for item in status)
        or len(status) != 0
    ):
        raise CampaignBootstrapError(
            f"{label} is not the requested clean source identity"
        )
    return {
        "repo_root": str(ROOT.resolve()),
        "head_sha": expected_source_sha,
        "status_lines": (),
    }


def _path_payload(
    identity: BlindPathIdentity,
) -> dict[str, Any]:
    payload = identity.payload()
    return {
        "path_id": payload["path_id"],
        "trial_id": payload["trial_id"],
        "nominal_h_nm": payload["nominal_h_nm"],
        "initial_plan_path": payload["initial_plan_path"],
        "initial_plan_sha256": payload["initial_plan_sha256"],
        "initial_space_authority_path": (
            payload["initial_space_authority_path"]
        ),
        "initial_space_authority_sha256": (
            payload["initial_space_authority_sha256"]
        ),
        "qualified_solver_config_path": (
            payload["qualified_solver_config_path"]
        ),
        "qualified_solver_config_sha256": (
            payload["qualified_solver_config_sha256"]
        ),
    }


def _handler_argv(
    *,
    source_sha: str,
    abi_sha256: str,
    paths: Sequence[Mapping[str, Any]],
    runtime: Mapping[str, Any],
) -> tuple[str, ...]:
    argv = [
        str(runtime["python_executable"]),
        "-m",
        HANDLER_MODULE,
        "--campaign-root",
        str(runtime["campaign_root"]),
        "--source-sha",
        source_sha,
        "--abi-sha256",
        abi_sha256,
        "--artifact-root",
        str(runtime["artifact_root"]),
        "--tensor-cache-directory",
        str(runtime["tensor_cache_directory"]),
        "--python-executable",
        str(runtime["python_executable"]),
        "--timeout-seconds",
        str(float(runtime["timeout_seconds"])),
    ]
    for row in paths:
        lane = str(row["path_id"]).lower()
        argv.extend(
            (
                f"--path-{lane}-plan",
                str(row["initial_plan_path"]),
                f"--path-{lane}-plan-sha256",
                str(row["initial_plan_sha256"]),
                f"--path-{lane}-initial-space-authority",
                str(row["initial_space_authority_path"]),
                f"--path-{lane}-initial-space-authority-sha256",
                str(row["initial_space_authority_sha256"]),
                f"--path-{lane}-qualified-solver-config",
                str(row["qualified_solver_config_path"]),
                f"--path-{lane}-qualified-solver-config-sha256",
                str(row["qualified_solver_config_sha256"]),
                f"--path-{lane}-trial-id",
                str(row["trial_id"]),
            )
        )
    return tuple(argv)


def _validated_manifest(
    payload: Mapping[str, Any],
    *,
    manifest_path: Path,
) -> Mapping[str, Any]:
    row = _exact(payload, _ROOT_KEYS, label="campaign bootstrap manifest")
    unsigned = dict(row)
    observed_manifest_sha = _sha256(
        unsigned.pop("manifest_payload_sha256"),
        label="bootstrap manifest payload SHA-256",
    )
    if _json_sha256(unsigned) != observed_manifest_sha:
        raise CampaignBootstrapError(
            "campaign bootstrap manifest self-hash differs"
        )
    if (
        row["schema_version"] != BOOTSTRAP_SCHEMA
        or row["status"] != "qualified"
        or row["pass"] is not True
        or row["formal_mpi_size"] != FORMAL_MPI_SIZE
        or row["maximum_cycles"] != MAXIMUM_CYCLES
        or row["source_clean_verified"] is not True
        or row["source_stable_during_bootstrap"] is not True
        or row["abi_stable_during_bootstrap"] is not True
        or row["protected_inputs_consumed"] is not False
        or row["pde_executed"] is not False
        or row["ordinary_default_changed"] is not False
    ):
        raise CampaignBootstrapError(
            "campaign bootstrap fixed contract differs"
        )
    source = _source_sha(row["source_sha"])
    abi = _sha256(row["abi_sha256"], label="ABI SHA-256")
    _sha256(row["source_probe_sha256"], label="source probe SHA-256")

    raw_paths = row["paths"]
    if not isinstance(raw_paths, list) or len(raw_paths) != 2:
        raise CampaignBootstrapError(
            "campaign bootstrap requires exactly Path A and Path B"
        )
    paths: list[Mapping[str, Any]] = []
    campaign_paths: list[BlindPathIdentity] = []
    for index, expected_path_id in enumerate(("A", "B")):
        path_row = _exact(
            raw_paths[index],
            _PATH_KEYS,
            label=f"Path {expected_path_id} bootstrap identity",
        )
        expected_trial = (
            f"task035e-blind-path-{expected_path_id.lower()}"
        )
        expected_h = 20.0 if expected_path_id == "A" else 15.0
        if (
            path_row["path_id"] != expected_path_id
            or path_row["trial_id"] != expected_trial
            or float(path_row["nominal_h_nm"]) != expected_h
        ):
            raise CampaignBootstrapError(
                f"Path {expected_path_id} fixed identity differs"
            )
        for path_key, digest_key, label in (
            (
                "initial_plan_path",
                "initial_plan_sha256",
                "initial plan",
            ),
            (
                "initial_space_authority_path",
                "initial_space_authority_sha256",
                "initial-space authority",
            ),
            (
                "qualified_solver_config_path",
                "qualified_solver_config_sha256",
                "qualified solver config",
            ),
        ):
            _private_file(
                Path(str(path_row[path_key])),
                label=f"Path {expected_path_id} {label}",
                expected_sha256=str(path_row[digest_key]),
            )
        paths.append(path_row)
        campaign_paths.append(
            BlindPathIdentity(
                path_id=expected_path_id,
                trial_id=str(path_row["trial_id"]),
                nominal_h_nm=float(path_row["nominal_h_nm"]),
                initial_plan_path=Path(
                    str(path_row["initial_plan_path"])
                ),
                initial_plan_sha256=str(
                    path_row["initial_plan_sha256"]
                ),
                initial_space_authority_path=Path(
                    str(path_row["initial_space_authority_path"])
                ),
                initial_space_authority_sha256=str(
                    path_row["initial_space_authority_sha256"]
                ),
                qualified_solver_config_path=Path(
                    str(path_row["qualified_solver_config_path"])
                ),
                qualified_solver_config_sha256=str(
                    path_row["qualified_solver_config_sha256"]
                ),
            )
        )

    runtime = _exact(
        row["runtime"],
        _RUNTIME_KEYS,
        label="campaign bootstrap runtime",
    )
    output_root = _validated_formal_output_root(
        Path(str(runtime["output_root"])),
    )
    if manifest_path.resolve() != output_root / MANIFEST_NAME:
        raise CampaignBootstrapError(
            "bootstrap manifest is outside its declared output root"
        )
    for key, label in (
        ("campaign_root", "campaign root"),
        ("artifact_root", "artifact root"),
        ("tensor_cache_directory", "tensor-cache directory"),
    ):
        directory = _private_directory(
            Path(str(runtime[key])),
            label=label,
        )
        if not directory.is_relative_to(output_root):
            raise CampaignBootstrapError(
                f"{label} is outside the bootstrap output root"
            )
    python = _absolute_linux_path(
        Path(str(runtime["python_executable"])),
        label="qualified Python executable",
        allow_final_symlink=True,
    )
    expected_python = Path(
        os.path.abspath(str(ROOT / ".venv" / "bin" / "python"))
    )
    if (
        Path(str(runtime["python_executable"])) != expected_python
        or not python.is_file()
    ):
        raise CampaignBootstrapError(
            "qualified Python executable differs from the repository venv"
        )
    if (
        not isinstance(runtime["timeout_seconds"], (int, float))
        or isinstance(runtime["timeout_seconds"], bool)
        or float(runtime["timeout_seconds"]) != DEFAULT_TIMEOUT_SECONDS
    ):
        raise CampaignBootstrapError(
            "campaign bootstrap timeout contract differs"
        )
    campaign_identity = _private_file(
        Path(str(runtime["campaign_identity_path"])),
        label="campaign identity",
        expected_sha256=str(runtime["campaign_identity_sha256"]),
    )
    if campaign_identity != (
        Path(str(runtime["campaign_root"])) / "campaign.json"
    ).resolve():
        raise CampaignBootstrapError(
            "campaign identity path differs from campaign root"
        )
    try:
        campaign_outer = json.loads(
            campaign_identity.read_text(encoding="utf-8"),
            parse_constant=_reject_nonfinite,
            object_pairs_hook=_reject_duplicate_object,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CampaignBootstrapError(
            "campaign identity is not strict JSON"
        ) from exc
    expected_campaign_payload = BlindCampaignIdentity(
        source_sha=source,
        abi_sha256=abi,
        paths=(campaign_paths[0], campaign_paths[1]),
    ).payload()
    expected_campaign_outer = {
        "schema_version": CAMPAIGN_SCHEMA,
        "sha256": _json_sha256(expected_campaign_payload),
        "payload": expected_campaign_payload,
    }
    if (
        not isinstance(campaign_outer, Mapping)
        or dict(campaign_outer) != expected_campaign_outer
    ):
        raise CampaignBootstrapError(
            "campaign identity does not replay from bootstrap inputs"
        )

    handler = _exact(
        row["handler"],
        _HANDLER_KEYS,
        label="campaign handler launch",
    )
    argv = handler["argv"]
    if (
        handler["module"] != HANDLER_MODULE
        or not isinstance(argv, list)
        or any(not isinstance(item, str) for item in argv)
        or tuple(argv)
        != _handler_argv(
            source_sha=source,
            abi_sha256=abi,
            paths=paths,
            runtime=runtime,
        )
        or _sha256(
            handler["argv_sha256"],
            label="handler argv SHA-256",
        )
        != _json_sha256(argv)
    ):
        raise CampaignBootstrapError(
            "campaign handler argv contract differs"
        )
    return row


def load_campaign_bootstrap_manifest(
    path: Path,
) -> Mapping[str, Any]:
    """Load and replay one immutable formal bootstrap manifest."""

    resolved = _private_file(path, label="campaign bootstrap manifest")
    try:
        payload = json.loads(
            resolved.read_text(encoding="utf-8"),
            parse_constant=_reject_nonfinite,
            object_pairs_hook=_reject_duplicate_object,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CampaignBootstrapError(
            "campaign bootstrap manifest is not strict JSON"
        ) from exc
    if not isinstance(payload, Mapping):
        raise CampaignBootstrapError(
            "campaign bootstrap manifest must be one JSON object"
        )
    return dict(_validated_manifest(payload, manifest_path=resolved))


def write_campaign_bootstrap(
    output_root: Path,
    *,
    verified_clean_source_sha: str,
) -> CampaignBootstrapReceipt:
    """Create two qualified starting paths and one closed handler launch."""

    source = _source_sha(verified_clean_source_sha)
    root = _new_output_root(output_root)
    source_before = _validated_source_state(
        _git_source_state(),
        expected_source_sha=source,
        label="source identity before campaign bootstrap",
    )
    abi_before = _sha256(
        live_qualified_abi_sha256(),
        label="live qualified ABI SHA-256 before campaign bootstrap",
    )

    inputs = _make_private_directory(root, "inputs")
    path_directories = {
        path_id: _make_private_directory(
            inputs,
            f"path-{path_id.lower()}",
        )
        for path_id in ("A", "B")
    }
    runtime_root = _make_private_directory(root, "runtime")
    campaign_root = _make_private_directory(runtime_root, "campaign")
    artifact_root = _make_private_directory(runtime_root, "artifacts")
    tensor_cache = _make_private_directory(runtime_root, "tensor-cache")

    identities: list[BlindPathIdentity] = []
    for path_id in ("A", "B"):
        directory = path_directories[path_id]
        plan_path = directory / "initial-plan.json"
        authority_path = directory / "initial-space-authority.json"
        initial = write_initial_space_bundle(
            path_id=path_id,
            source_sha=source,
            plan_path=plan_path,
            authority_path=authority_path,
            mpi_size=FORMAL_MPI_SIZE,
        )
        config_path = directory / "qualified-solver-config.json"
        config = trial_metadata.write_qualified_solver_config(
            config_path,
            initial_plan_path=plan_path,
            verified_clean_source_sha=source,
            path_id=path_id,
        )
        identities.append(
            BlindPathIdentity(
                path_id=path_id,
                trial_id=(
                    f"task035e-blind-path-{path_id.lower()}"
                ),
                nominal_h_nm=(20.0 if path_id == "A" else 15.0),
                initial_plan_path=initial.plan_path,
                initial_plan_sha256=initial.plan_sha256,
                initial_space_authority_path=initial.authority_path,
                initial_space_authority_sha256=(
                    initial.authority_sha256
                ),
                qualified_solver_config_path=config.path,
                qualified_solver_config_sha256=config.file_sha256,
            )
        )

    campaign_identity = BlindCampaignIdentity(
        source_sha=source,
        abi_sha256=abi_before,
        paths=(identities[0], identities[1]),
    )
    initialize_campaign(campaign_root, campaign_identity)
    campaign_identity_path = campaign_root / "campaign.json"

    python_executable = Path(os.path.abspath(sys.executable))
    runtime = {
        "output_root": str(root),
        "campaign_root": str(campaign_root),
        "campaign_identity_path": str(campaign_identity_path),
        "campaign_identity_sha256": _file_sha256(
            campaign_identity_path
        ),
        "artifact_root": str(artifact_root),
        "tensor_cache_directory": str(tensor_cache),
        "python_executable": str(python_executable),
        "timeout_seconds": DEFAULT_TIMEOUT_SECONDS,
    }
    path_payloads = [_path_payload(identity) for identity in identities]
    handler_argv = _handler_argv(
        source_sha=source,
        abi_sha256=abi_before,
        paths=path_payloads,
        runtime=runtime,
    )

    source_after = _validated_source_state(
        _git_source_state(),
        expected_source_sha=source,
        label="source identity after campaign bootstrap",
    )
    abi_after = _sha256(
        live_qualified_abi_sha256(),
        label="live qualified ABI SHA-256 after campaign bootstrap",
    )
    if source_after != source_before:
        raise CampaignBootstrapError(
            "source identity changed during campaign bootstrap"
        )
    if abi_after != abi_before:
        raise CampaignBootstrapError(
            "qualified ABI identity changed during campaign bootstrap"
        )

    unsigned: dict[str, Any] = {
        "schema_version": BOOTSTRAP_SCHEMA,
        "status": "qualified",
        "pass": True,
        "source_sha": source,
        "source_probe_sha256": _json_sha256(source_before),
        "abi_sha256": abi_before,
        "formal_mpi_size": FORMAL_MPI_SIZE,
        "maximum_cycles": MAXIMUM_CYCLES,
        "paths": path_payloads,
        "runtime": runtime,
        "handler": {
            "module": HANDLER_MODULE,
            "argv": list(handler_argv),
            "argv_sha256": _json_sha256(handler_argv),
        },
        "source_clean_verified": True,
        "source_stable_during_bootstrap": True,
        "abi_stable_during_bootstrap": True,
        "protected_inputs_consumed": False,
        "pde_executed": False,
        "ordinary_default_changed": False,
    }
    payload = {
        **unsigned,
        "manifest_payload_sha256": _json_sha256(unsigned),
    }
    manifest_path = root / MANIFEST_NAME
    _validated_manifest(payload, manifest_path=manifest_path)
    manifest_file_sha = _atomic_private_json(manifest_path, payload)
    loaded = load_campaign_bootstrap_manifest(manifest_path)
    if dict(loaded) != payload:
        raise CampaignBootstrapError(
            "campaign bootstrap manifest changed during publication"
        )
    return CampaignBootstrapReceipt(
        manifest_path=manifest_path,
        manifest_file_sha256=manifest_file_sha,
        manifest_payload_sha256=payload[
            "manifest_payload_sha256"
        ],
        source_sha=source,
        abi_sha256=abi_before,
        handler_argv=handler_argv,
    )


def _parse_args(
    argv: Sequence[str] | None = None,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--verified-clean-sha", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        receipt = write_campaign_bootstrap(
            args.output_root,
            verified_clean_source_sha=args.verified_clean_sha,
        )
    except (
        CampaignBootstrapError,
        FileExistsError,
        OSError,
        subprocess.SubprocessError,
        trial_metadata.TrialMetadataError,
    ) as error:
        print(
            json.dumps(
                {
                    "schema_version": BOOTSTRAP_RECEIPT_SCHEMA,
                    "status": "failed",
                    "error": str(error),
                    "output_root": str(args.output_root),
                    "pde_executed": False,
                    "ordinary_default_changed": False,
                },
                sort_keys=True,
            )
        )
        return 2
    print(
        json.dumps(
            {
                "schema_version": BOOTSTRAP_RECEIPT_SCHEMA,
                "status": "completed",
                "manifest_path": str(receipt.manifest_path),
                "manifest_file_sha256": (
                    receipt.manifest_file_sha256
                ),
                "manifest_payload_sha256": (
                    receipt.manifest_payload_sha256
                ),
                "source_sha": receipt.source_sha,
                "abi_sha256": receipt.abi_sha256,
                "handler_argv": list(receipt.handler_argv),
                "pde_executed": False,
                "ordinary_default_changed": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "BOOTSTRAP_SCHEMA",
    "CampaignBootstrapError",
    "CampaignBootstrapReceipt",
    "load_campaign_bootstrap_manifest",
    "main",
    "write_campaign_bootstrap",
]
