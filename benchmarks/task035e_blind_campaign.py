#!/usr/bin/env python3
"""Crash-resumable orchestration for the formal Task035e blind campaign.

This module is deliberately an orchestration layer, not a numerical solver.
It fixes the source, ABI, two initial plans, trial IDs, path order, MPI policy,
stage order, and evidence publication rules before any expensive solve starts.
Numerical stage implementations are injected through ``PreparedStage`` so the
framework can be tested without running a PDE.

The only accepted expensive command is an argv vector for
``benchmarks.run_task033_full3d_watchdog``.  It is never passed through a
shell.  A host-wide ``flock`` serializes expensive stages across campaign
roots.  Completion is reconstructed exclusively from immutable, self-hashed
receipts and revalidated artifact hashes; no mutable cursor is trusted.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
from typing import Any, Callable, Iterator, Mapping, Protocol, Sequence


CAMPAIGN_SCHEMA = "task035e.blind-campaign-identity.v2"
STAGE_RECEIPT_SCHEMA = "task035e.blind-campaign-stage-receipt.v4"
ATTEMPT_INTENT_SCHEMA = "task035e.blind-campaign-attempt-intent.v2"
ATTEMPT_PROCESS_SCHEMA = "task035e.blind-campaign-attempt-process.v2"
COMMAND_EXECUTION_RECEIPT_SCHEMA = (
    "task035e.blind-campaign-command-execution-receipt.v1"
)
INTERRUPTED_ATTEMPT_SCHEMA = (
    "task035e.blind-campaign-interrupted-attempt.v2"
)
CAMPAIGN_REPORT_SCHEMA = "task035e.blind-campaign-run-report.v2"
WATCHDOG_MODULE = "benchmarks.run_task033_full3d_watchdog"
FORMAL_MPI_SIZE = 8
FINAL_SERIAL_MPI_SIZE = 1
MAXIMUM_CYCLES = 6
FINAL_INTERNAL_PROBE_ORDER = (
    "algebraic",
    "dtn",
    "postprocess",
    "serial_mpi1",
)
DEFAULT_HEAVY_LOCK_PATH = Path(
    "/tmp/myfenics-task035e-single-heavy-pde.lock"
)

_SOURCE_SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_TRIAL_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_CLASSIFICATION_RE = re.compile(r"[a-z][a-z0-9_.-]{0,127}\Z")
_ARTIFACT_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
_ARTIFACT_ROLE_RE = re.compile(r"[a-z][a-z0-9_]{0,127}\Z")
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
_CYCLE_STAGE_NAMES = (
    "current_solve",
    "shadow_target_discovery",
    "p_shadow_discovery",
    "h_shadow_discovery",
    "cellwise_partition",
    "goal_marking",
    "p_selected_shadow_verification",
    "h_selected_shadow_verification",
    "shadow_bundle",
    "internal_gate_deferred_or_final",
    "isolation_audit",
    "cycle_binding",
    "cycle_advance",
    "transition_or_pkeep",
)
_FINAL_STAGE_NAMES = (
    "two_start_comparison",
    "candidate_freeze",
)
_HEAVY_STAGE_NAMES = frozenset(
    {
        "current_solve",
        "p_shadow_discovery",
        "h_shadow_discovery",
        "p_selected_shadow_verification",
        "h_selected_shadow_verification",
        "internal_gate_deferred_or_final",
    }
)
_ALLOWED_RESULT_STATUSES = frozenset({"completed", "controlled_negative"})
_ALLOWED_LANE_DECISIONS = frozenset(
    {"continue", "freeze_ready", "controlled_negative"}
)
_ALLOWED_SATURATION_STATES = frozenset(
    {"verified", "unknown", "not_applicable"}
)


class BlindCampaignError(ValueError):
    """Base class for fail-closed campaign errors."""


class CampaignIdentityDrift(BlindCampaignError):
    """Raised when source, ABI, plan, trial, or path identity changes."""


class CampaignEvidenceError(BlindCampaignError):
    """Raised when immutable campaign evidence is missing or altered."""


class HeavyStageBusy(BlindCampaignError):
    """Raised when another host process owns the expensive-stage lock."""


class StageAlreadyRunning(BlindCampaignError):
    """Raised when a prior attempt still has a live recorded process."""


class CommandExecutionError(BlindCampaignError):
    """Raised when a declared watchdog invocation does not complete."""


def _reject_nonfinite(value: str) -> None:
    raise CampaignEvidenceError(
        f"non-finite JSON constant is forbidden: {value}"
    )


def _reject_duplicate_object(
    pairs: Sequence[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CampaignEvidenceError(
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
    result = str(value)
    if _SOURCE_SHA_RE.fullmatch(result) is None:
        raise BlindCampaignError(
            "source_sha must be one lowercase 40-character Git SHA"
        )
    return result


def _sha256(value: Any, *, label: str) -> str:
    result = str(value)
    if _SHA256_RE.fullmatch(result) is None:
        raise BlindCampaignError(f"{label} must be one lowercase SHA-256")
    return result


def _trial_id(value: Any, *, label: str) -> str:
    result = str(value)
    if _TRIAL_ID_RE.fullmatch(result) is None:
        raise BlindCampaignError(f"{label} is not a valid trial ID")
    return result


def _classification(value: Any) -> str:
    result = str(value)
    if _CLASSIFICATION_RE.fullmatch(result) is None:
        raise BlindCampaignError(
            "classification must be one lowercase opaque identifier"
        )
    return result


@contextmanager
def _private_umask() -> Iterator[None]:
    previous = os.umask(0o077)
    try:
        yield
    finally:
        os.umask(previous)


def _safe_path(path: Path, *, label: str) -> Path:
    if path.is_symlink():
        raise CampaignEvidenceError(f"{label} must not be a symlink")
    resolved = path.expanduser().resolve()
    lowered = {part.lower() for part in resolved.parts}
    if lowered.intersection(_PROTECTED_PATH_PARTS):
        raise CampaignEvidenceError(f"{label} crosses a protected layer")
    return resolved


def _require_private_file(
    path: Path,
    *,
    label: str,
    expected_sha256: str | None = None,
) -> Path:
    resolved = _safe_path(path, label=label)
    try:
        metadata = resolved.stat()
    except OSError as exc:
        raise CampaignEvidenceError(
            f"{label} is not readable: {resolved}"
        ) from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise CampaignEvidenceError(f"{label} is not a regular file")
    if stat.S_IMODE(metadata.st_mode) != 0o600:
        raise CampaignEvidenceError(f"{label} must use mode 0600")
    if (
        expected_sha256 is not None
        and _file_sha256(resolved)
        != _sha256(expected_sha256, label=f"{label} SHA-256")
    ):
        raise CampaignEvidenceError(f"{label} SHA-256 differs")
    return resolved


def _ensure_private_directory(path: Path, *, label: str) -> Path:
    if path.is_symlink():
        raise CampaignEvidenceError(f"{label} must not be a symlink")
    with _private_umask():
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
    resolved = path.resolve()
    metadata = resolved.stat()
    if not stat.S_ISDIR(metadata.st_mode):
        raise CampaignEvidenceError(f"{label} is not a directory")
    if stat.S_IMODE(metadata.st_mode) != 0o700:
        raise CampaignEvidenceError(f"{label} must use mode 0700")
    return resolved


def _atomic_private_write(path: Path, payload: bytes) -> str:
    if path.exists() or path.is_symlink():
        raise FileExistsError(f"refusing to overwrite immutable file: {path}")
    parent = _ensure_private_directory(path.parent, label="artifact directory")
    with _private_umask():
        descriptor, temporary_name = tempfile.mkstemp(
            dir=parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
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
    return hashlib.sha256(payload).hexdigest()


def _outer_payload(
    schema_version: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": schema_version,
        "sha256": _json_sha256(payload),
        "payload": _canonical(payload),
    }


def _write_outer(
    path: Path,
    *,
    schema_version: str,
    payload: Mapping[str, Any],
) -> str:
    return _atomic_private_write(
        path,
        _canonical_bytes(_outer_payload(schema_version, payload)),
    )


def _strict_json(path: Path, *, label: str) -> Mapping[str, Any]:
    resolved = _require_private_file(path, label=label)
    try:
        value = json.loads(
            resolved.read_text(encoding="ascii"),
            parse_constant=_reject_nonfinite,
            object_pairs_hook=_reject_duplicate_object,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CampaignEvidenceError(f"cannot parse {label}") from exc
    if not isinstance(value, Mapping):
        raise CampaignEvidenceError(f"{label} must be one JSON object")
    return value


def _load_outer(
    path: Path,
    *,
    schema_version: str,
    label: str,
) -> Mapping[str, Any]:
    value = _strict_json(path, label=label)
    if set(value) != {"schema_version", "sha256", "payload"}:
        raise CampaignEvidenceError(f"{label} does not use its closed wrapper")
    payload = value["payload"]
    if not isinstance(payload, Mapping):
        raise CampaignEvidenceError(f"{label} payload must be one object")
    if (
        value["schema_version"] != schema_version
        or _sha256(value["sha256"], label=f"{label} payload SHA-256")
        != _json_sha256(payload)
    ):
        raise CampaignEvidenceError(f"{label} schema or self-hash differs")
    return payload


@dataclass(frozen=True, slots=True)
class BlindPathIdentity:
    """Immutable identity of one blind starting path."""

    path_id: str
    trial_id: str
    nominal_h_nm: float
    initial_plan_path: Path
    initial_plan_sha256: str
    initial_space_authority_path: Path
    initial_space_authority_sha256: str
    qualified_solver_config_path: Path
    qualified_solver_config_sha256: str

    def __post_init__(self) -> None:
        normalized = str(self.path_id).upper()
        if normalized not in {"A", "B"}:
            raise BlindCampaignError("path_id must be A or B")
        expected_h = {"A": 20.0, "B": 15.0}[normalized]
        if float(self.nominal_h_nm) != expected_h:
            raise BlindCampaignError(
                f"Path {normalized} requires nominal h={expected_h:g} nm"
            )
        _trial_id(self.trial_id, label=f"Path {normalized} trial_id")
        _sha256(
            self.initial_plan_sha256,
            label=f"Path {normalized} initial plan SHA-256",
        )
        _sha256(
            self.initial_space_authority_sha256,
            label=(
                f"Path {normalized} initial-space authority SHA-256"
            ),
        )
        _sha256(
            self.qualified_solver_config_sha256,
            label=(
                f"Path {normalized} qualified solver-config SHA-256"
            ),
        )
        object.__setattr__(self, "path_id", normalized)
        object.__setattr__(self, "nominal_h_nm", expected_h)
        object.__setattr__(
            self,
            "initial_plan_path",
            Path(self.initial_plan_path),
        )
        object.__setattr__(
            self,
            "initial_space_authority_path",
            Path(self.initial_space_authority_path),
        )
        object.__setattr__(
            self,
            "qualified_solver_config_path",
            Path(self.qualified_solver_config_path),
        )

    def validate_plan(self) -> Path:
        return _require_private_file(
            self.initial_plan_path,
            label=f"Path {self.path_id} initial plan",
            expected_sha256=self.initial_plan_sha256,
        )

    def validate_initial_space_authority(self) -> Path:
        return _require_private_file(
            self.initial_space_authority_path,
            label=f"Path {self.path_id} initial-space authority",
            expected_sha256=self.initial_space_authority_sha256,
        )

    def validate_qualified_solver_config(self) -> Path:
        return _require_private_file(
            self.qualified_solver_config_path,
            label=f"Path {self.path_id} qualified solver config",
            expected_sha256=self.qualified_solver_config_sha256,
        )

    def payload(self) -> dict[str, Any]:
        return {
            "path_id": self.path_id,
            "trial_id": self.trial_id,
            "nominal_h_nm": self.nominal_h_nm,
            "initial_plan_path": str(self.validate_plan()),
            "initial_plan_sha256": self.initial_plan_sha256,
            "initial_space_authority_path": str(
                self.validate_initial_space_authority()
            ),
            "initial_space_authority_sha256": (
                self.initial_space_authority_sha256
            ),
            "qualified_solver_config_path": str(
                self.validate_qualified_solver_config()
            ),
            "qualified_solver_config_sha256": (
                self.qualified_solver_config_sha256
            ),
        }


@dataclass(frozen=True, slots=True)
class BlindCampaignIdentity:
    """Closed source/ABI/path identity for a two-start campaign."""

    source_sha: str
    abi_sha256: str
    paths: tuple[BlindPathIdentity, BlindPathIdentity]
    formal_mpi_size: int = FORMAL_MPI_SIZE
    maximum_cycles: int = MAXIMUM_CYCLES

    def __post_init__(self) -> None:
        _source_sha(self.source_sha)
        _sha256(self.abi_sha256, label="ABI SHA-256")
        if int(self.formal_mpi_size) != FORMAL_MPI_SIZE:
            raise BlindCampaignError("formal campaign execution requires MPI8")
        if int(self.maximum_cycles) != MAXIMUM_CYCLES:
            raise BlindCampaignError("Task035e fixes maximum_cycles=6")
        if len(self.paths) != 2:
            raise BlindCampaignError("campaign requires exactly Path A and B")
        if tuple(path.path_id for path in self.paths) != ("A", "B"):
            raise BlindCampaignError("Path A must precede Path B")
        if self.paths[0].trial_id == self.paths[1].trial_id:
            raise BlindCampaignError("Path A and B trial IDs must differ")

    def validate(self) -> None:
        for path in self.paths:
            path.validate_plan()
            path.validate_initial_space_authority()
            path.validate_qualified_solver_config()

    def payload(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": CAMPAIGN_SCHEMA,
            "status": "identity_frozen",
            "source_sha": self.source_sha,
            "abi_sha256": self.abi_sha256,
            "formal_mpi_size": FORMAL_MPI_SIZE,
            "maximum_cycles": MAXIMUM_CYCLES,
            "final_internal_probe_order": list(FINAL_INTERNAL_PROBE_ORDER),
            "path_order": ["A", "B"],
            "paths": [path.payload() for path in self.paths],
            "ordinary_default_changed": False,
        }


@dataclass(frozen=True, slots=True)
class CampaignStage:
    """One node in the deterministic two-path stage DAG."""

    ordinal: int
    path_id: str
    cycle_index: int | None
    stage_name: str
    heavy: bool
    predecessor_stage_id: str | None

    @property
    def stage_id(self) -> str:
        if self.path_id == "FINAL":
            return f"campaign-final-{self.stage_name}"
        if self.cycle_index is None:
            suffix = "bootstrap"
        else:
            suffix = f"cycle-{self.cycle_index}"
        return f"path-{self.path_id.lower()}-{suffix}-{self.stage_name}"


def build_campaign_stage_dag(
    identity: BlindCampaignIdentity,
) -> tuple[CampaignStage, ...]:
    """Return Path-A-first, then Path-B, six-cycle formal stage DAG."""

    stages: list[CampaignStage] = []
    ordinal = 0
    final_predecessor: str | None = None
    for path in identity.paths:
        previous: str | None = None
        initial = CampaignStage(
            ordinal=ordinal,
            path_id=path.path_id,
            cycle_index=None,
            stage_name="initial_plan",
            heavy=False,
            predecessor_stage_id=None,
        )
        stages.append(initial)
        ordinal += 1
        previous = initial.stage_id
        for cycle_index in range(identity.maximum_cycles):
            for stage_name in _CYCLE_STAGE_NAMES:
                stage = CampaignStage(
                    ordinal=ordinal,
                    path_id=path.path_id,
                    cycle_index=cycle_index,
                    stage_name=stage_name,
                    heavy=stage_name in _HEAVY_STAGE_NAMES,
                    predecessor_stage_id=previous,
                )
                stages.append(stage)
                ordinal += 1
                previous = stage.stage_id
        final_predecessor = previous
    for stage_name in _FINAL_STAGE_NAMES:
        stage = CampaignStage(
            ordinal=ordinal,
            path_id="FINAL",
            cycle_index=None,
            stage_name=stage_name,
            heavy=False,
            predecessor_stage_id=final_predecessor,
        )
        stages.append(stage)
        ordinal += 1
        final_predecessor = stage.stage_id
    return tuple(stages)


@dataclass(frozen=True, slots=True)
class StageArtifactBinding:
    """One typed immutable artifact made available to a later stage."""

    role: str
    path: Path
    sha256: str
    size_bytes: int

    def __post_init__(self) -> None:
        if _ARTIFACT_ROLE_RE.fullmatch(str(self.role)) is None:
            raise BlindCampaignError("artifact role is not canonical")
        _sha256(self.sha256, label=f"{self.role} artifact SHA-256")
        if type(self.size_bytes) is not int or self.size_bytes < 0:
            raise BlindCampaignError("artifact size must be nonnegative")
        object.__setattr__(self, "path", Path(self.path))

    @classmethod
    def from_file(
        cls,
        role: str,
        path: Path,
    ) -> "StageArtifactBinding":
        resolved = _require_private_file(
            Path(path),
            label=f"{role} artifact",
        )
        return cls(
            role=role,
            path=resolved,
            sha256=_file_sha256(resolved),
            size_bytes=resolved.stat().st_size,
        )

    def validate(self) -> Path:
        resolved = _require_private_file(
            self.path,
            label=f"{self.role} artifact",
            expected_sha256=self.sha256,
        )
        if resolved.stat().st_size != self.size_bytes:
            raise CampaignEvidenceError(
                f"{self.role} artifact size differs"
            )
        return resolved

    def payload(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "path": str(self.validate()),
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }


@dataclass(frozen=True, slots=True)
class StageExecutionContext:
    """Hash-bound context passed to one injected stage implementation."""

    campaign_root: Path
    stage: CampaignStage
    source_sha: str
    abi_sha256: str
    trial_id: str
    nominal_h_nm: float
    input_plan_sha256: str
    input_artifacts: tuple[StageArtifactBinding, ...]

    def __post_init__(self) -> None:
        roles = tuple(binding.role for binding in self.input_artifacts)
        if len(set(roles)) != len(roles):
            raise BlindCampaignError(
                "stage input artifact roles must be unique"
            )
        for binding in self.input_artifacts:
            binding.validate()

    def artifact(self, role: str) -> StageArtifactBinding:
        matches = tuple(
            binding
            for binding in self.input_artifacts
            if binding.role == role
        )
        if len(matches) != 1:
            raise CampaignEvidenceError(
                f"stage requires exactly one {role} artifact"
            )
        return matches[0]


@dataclass(frozen=True, slots=True)
class StageResult:
    """Closed result returned by one injected stage implementation."""

    status: str
    classification: str
    input_plan_sha256: str
    artifacts: tuple[StageArtifactBinding, ...]
    command_receipt_file_sha256s: tuple[str, ...] = ()
    next_plan_sha256: str | None = None
    lane_decision: str = "continue"
    freeze_requested: bool = False
    p6_saturation: str = "not_applicable"
    h_level3_saturation: str = "not_applicable"

    def __post_init__(self) -> None:
        if self.status not in _ALLOWED_RESULT_STATUSES:
            raise BlindCampaignError("stage result status is not allowed")
        _classification(self.classification)
        _sha256(self.input_plan_sha256, label="stage input plan SHA-256")
        if self.next_plan_sha256 is not None:
            _sha256(
                self.next_plan_sha256,
                label="stage next plan SHA-256",
            )
        if self.lane_decision not in _ALLOWED_LANE_DECISIONS:
            raise BlindCampaignError("stage lane decision is not allowed")
        if self.p6_saturation not in _ALLOWED_SATURATION_STATES:
            raise BlindCampaignError("p6 saturation state is not allowed")
        if self.h_level3_saturation not in _ALLOWED_SATURATION_STATES:
            raise BlindCampaignError(
                "level3 h saturation state is not allowed"
            )
        if type(self.freeze_requested) is not bool:
            raise BlindCampaignError("freeze_requested must be boolean")
        roles = tuple(binding.role for binding in self.artifacts)
        if not roles or len(set(roles)) != len(roles):
            raise BlindCampaignError(
                "stage result requires unique typed artifacts"
            )
        for binding in self.artifacts:
            binding.validate()
        for index, value in enumerate(
            self.command_receipt_file_sha256s
        ):
            _sha256(
                value,
                label=f"stage command receipt {index} file SHA-256",
            )


@dataclass(frozen=True, slots=True)
class PreparedStage:
    """Prevalidated execution closure and its optional expensive argv."""

    execute: Callable[
        [
            "AttemptHandle",
            tuple["CommandExecutionReceipt", ...],
        ],
        StageResult,
    ]
    argv: tuple[str, ...] | None = None
    argvs: tuple[tuple[str, ...], ...] = ()

    def __post_init__(self) -> None:
        if self.argv is not None and self.argvs:
            raise BlindCampaignError(
                "PreparedStage cannot mix argv and argvs"
            )

    @property
    def command_argvs(self) -> tuple[tuple[str, ...], ...]:
        if self.argv is not None:
            return (tuple(self.argv),)
        return tuple(tuple(argv) for argv in self.argvs)


class StagePreparer(Protocol):
    def __call__(
        self,
        context: StageExecutionContext,
        attempt: "AttemptHandle",
    ) -> PreparedStage: ...


@dataclass(frozen=True, slots=True)
class WatchdogLaunchSpec:
    """Inputs for one real watchdog argv; building never executes it."""

    python_executable: Path
    source_sha: str
    path_id: str
    nominal_h_nm: float
    trial_id: str
    cycle_index: int
    output_role: str
    plan_path: Path
    plan_sha256: str
    artifact_root: Path
    tensor_cache_directory: Path
    run_dir: Path
    record_path: Path
    mpi_size: int = FORMAL_MPI_SIZE
    current_snapshot_path: Path | None = None
    current_snapshot_sha256: str | None = None
    transition_action_path: Path | None = None
    transition_action_sha256: str | None = None
    internal_probe_kind: str | None = None
    probe_dtn_max_m: int | None = None
    probe_dtn_max_n: int | None = None
    probe_surface_quadrature_degree: int | None = None
    final_internal_gate: bool = False
    timeout_seconds: float = 43200.0


def _absolute_linux_path(path: Path, *, label: str) -> Path:
    expanded = Path(path).expanduser()
    if not expanded.is_absolute():
        raise BlindCampaignError(f"{label} must be absolute")
    normalized = Path(os.path.abspath(str(expanded)))
    text = normalized.as_posix()
    if text == "/mnt" or text.startswith("/mnt/"):
        raise BlindCampaignError(f"{label} must be on the Linux filesystem")
    return normalized


def build_watchdog_argv(spec: WatchdogLaunchSpec) -> tuple[str, ...]:
    """Build, validate, and return one no-shell formal watchdog argv."""

    source_sha = _source_sha(spec.source_sha)
    path_id = str(spec.path_id).upper()
    if path_id not in {"A", "B"}:
        raise BlindCampaignError("watchdog path_id must be A or B")
    expected_h = {"A": 20.0, "B": 15.0}[path_id]
    if float(spec.nominal_h_nm) != expected_h:
        raise BlindCampaignError("watchdog h does not match its path")
    trial_id = _trial_id(spec.trial_id, label="watchdog trial_id")
    if (
        type(spec.cycle_index) is not int
        or not 0 <= spec.cycle_index < MAXIMUM_CYCLES
    ):
        raise BlindCampaignError("watchdog cycle_index must be in [0, 5]")
    if spec.output_role not in {"current", "p-shadow", "h-shadow"}:
        raise BlindCampaignError("watchdog output_role is not allowed")

    plan_path = _require_private_file(
        spec.plan_path,
        label="watchdog plan",
        expected_sha256=spec.plan_sha256,
    )
    python = _absolute_linux_path(
        spec.python_executable,
        label="Python executable",
    )
    if not python.is_file():
        raise BlindCampaignError("Python executable is missing")
    artifact_root = _absolute_linux_path(
        spec.artifact_root,
        label="artifact root",
    )
    tensor_cache = _absolute_linux_path(
        spec.tensor_cache_directory,
        label="tensor cache",
    )
    run_dir = _absolute_linux_path(spec.run_dir, label="run directory")
    record_path = _absolute_linux_path(spec.record_path, label="record path")

    probe = spec.internal_probe_kind
    allowed_probes = {"algebraic", "dtn", "postprocess", "serial_mpi1"}
    if probe is not None and probe not in allowed_probes:
        raise BlindCampaignError("internal probe kind is not allowed")
    mpi_size = int(spec.mpi_size)
    if mpi_size == 2:
        raise BlindCampaignError("MPI2 is forbidden in Task035e campaign runs")
    if probe == "serial_mpi1":
        if mpi_size != FINAL_SERIAL_MPI_SIZE:
            raise BlindCampaignError("serial_mpi1 is the sole MPI1 probe")
        if spec.final_internal_gate is not True:
            raise BlindCampaignError(
                "serial_mpi1 is allowed only at the final internal Gate"
            )
    elif mpi_size != FORMAL_MPI_SIZE:
        raise BlindCampaignError("formal blind solves and probes require MPI8")
    if mpi_size == 1 and probe != "serial_mpi1":
        raise BlindCampaignError("MPI1 is restricted to final serial_mpi1")

    snapshot_pair = (
        spec.current_snapshot_path,
        spec.current_snapshot_sha256,
    )
    action_pair = (
        spec.transition_action_path,
        spec.transition_action_sha256,
    )
    if (snapshot_pair[0] is None) != (snapshot_pair[1] is None):
        raise BlindCampaignError("snapshot path/hash must be supplied together")
    if (action_pair[0] is None) != (action_pair[1] is None):
        raise BlindCampaignError("action path/hash must be supplied together")

    initial_current = bool(
        spec.output_role == "current"
        and spec.cycle_index == 0
        and probe is None
    )
    if initial_current:
        if snapshot_pair[0] is not None or action_pair[0] is not None:
            raise BlindCampaignError(
                "initial current solve accepts no snapshot or transition"
            )
    elif probe is not None:
        if snapshot_pair[0] is None or action_pair[0] is not None:
            raise BlindCampaignError(
                "internal probes require a snapshot and no transition"
            )
        if spec.output_role != "current":
            raise BlindCampaignError("internal probes must use current role")
    elif snapshot_pair[0] is None or action_pair[0] is None:
        raise BlindCampaignError(
            "noninitial current and shadow solves require snapshot/action"
        )

    snapshot_path: Path | None = None
    if snapshot_pair[0] is not None:
        snapshot_path = _require_private_file(
            Path(snapshot_pair[0]),
            label="current snapshot",
            expected_sha256=str(snapshot_pair[1]),
        )
    action_path: Path | None = None
    if action_pair[0] is not None:
        action_path = _require_private_file(
            Path(action_pair[0]),
            label="transition action",
            expected_sha256=str(action_pair[1]),
        )

    argv = [
        str(python),
        "-m",
        WATCHDOG_MODULE,
        "--degree",
        "6",
        "--h-nm",
        f"{expected_h:g}",
        "--polarization-kind",
        "s",
        "--run-kind",
        "full-solve",
        "--mpi-size",
        str(mpi_size),
        "--profile",
        "default",
        "--stage4-full3d-assembly-backend",
        "assembly_time_variable_p_condensed",
        "--stage4-raw-tensor-cache",
        "--stage4-raw-tensor-cache-directory",
        str(tensor_cache),
        "--stage4-local-h-refinement-plan",
        str(plan_path),
        "--stage4-local-h-refinement-plan-sha256",
        spec.plan_sha256,
        "--task035e-blind-candidate-gate",
        "--task035e-blind-trial-id",
        trial_id,
        "--task035e-blind-cycle-index",
        str(spec.cycle_index),
        "--task035e-blind-output-role",
        spec.output_role,
        "--artifact-root",
        str(artifact_root),
        "--run-dir",
        str(run_dir),
        "--record",
        str(record_path),
        "--poll-interval",
        "0.25",
        "--timeout-seconds",
        f"{float(spec.timeout_seconds):g}",
        "--verified-clean-sha",
        source_sha,
    ]
    if snapshot_path is not None:
        argv.extend(
            (
                "--task035e-current-snapshot-manifest",
                str(snapshot_path),
                "--task035e-current-snapshot-manifest-sha256",
                str(snapshot_pair[1]),
            )
        )
    if action_path is not None:
        argv.extend(
            (
                "--task035e-transition-action",
                str(action_path),
                "--task035e-transition-action-sha256",
                str(action_pair[1]),
            )
        )
    if probe is not None:
        argv.extend(("--task035e-internal-probe-kind", probe))
        if probe == "dtn":
            if (
                type(spec.probe_dtn_max_m) is not int
                or spec.probe_dtn_max_m < 0
                or type(spec.probe_dtn_max_n) is not int
                or spec.probe_dtn_max_n < 0
            ):
                raise BlindCampaignError(
                    "DtN probe requires nonnegative max-m and max-n"
                )
            argv.extend(
                (
                    "--task035e-probe-dtn-max-m",
                    str(spec.probe_dtn_max_m),
                    "--task035e-probe-dtn-max-n",
                    str(spec.probe_dtn_max_n),
                )
            )
        elif (
            spec.probe_dtn_max_m is not None
            or spec.probe_dtn_max_n is not None
        ):
            raise BlindCampaignError("only the DtN probe accepts order limits")
        if probe == "postprocess":
            if (
                type(spec.probe_surface_quadrature_degree) is not int
                or spec.probe_surface_quadrature_degree < 1
            ):
                raise BlindCampaignError(
                    "postprocess probe requires positive quadrature degree"
                )
            argv.extend(
                (
                    "--task035e-probe-surface-quadrature-degree",
                    str(spec.probe_surface_quadrature_degree),
                )
            )
        elif spec.probe_surface_quadrature_degree is not None:
            raise BlindCampaignError(
                "only the postprocess probe accepts quadrature degree"
            )
    elif (
        spec.probe_dtn_max_m is not None
        or spec.probe_dtn_max_n is not None
        or spec.probe_surface_quadrature_degree is not None
    ):
        raise BlindCampaignError("probe parameters require a probe kind")

    result = tuple(argv)
    validate_watchdog_argv(result, expected_source_sha=source_sha)
    return result


def _option_values(argv: tuple[str, ...], option: str) -> tuple[str, ...]:
    values: list[str] = []
    for index, value in enumerate(argv):
        if value == option:
            if index + 1 >= len(argv) or argv[index + 1].startswith("--"):
                raise BlindCampaignError(f"{option} has no value")
            values.append(argv[index + 1])
    return tuple(values)


def _one_option(argv: tuple[str, ...], option: str) -> str:
    values = _option_values(argv, option)
    if len(values) != 1:
        raise BlindCampaignError(f"{option} must occur exactly once")
    return values[0]


def validate_watchdog_argv(
    argv: Sequence[str],
    *,
    expected_source_sha: str | None = None,
) -> tuple[str, ...]:
    """Validate the sole allowed expensive argv without executing it."""

    result = tuple(str(item) for item in argv)
    if len(result) < 3:
        raise BlindCampaignError("expensive argv is incomplete")
    if any("\x00" in item or "\n" in item for item in result):
        raise BlindCampaignError("expensive argv contains unsafe characters")
    executable = Path(result[0])
    if not executable.is_absolute():
        raise BlindCampaignError("expensive argv requires absolute Python")
    if not executable.name.startswith("python"):
        raise BlindCampaignError("expensive argv executable must be Python")
    if result[1:3] != ("-m", WATCHDOG_MODULE):
        raise BlindCampaignError(
            "expensive stages may call only the qualified watchdog module"
        )
    if "--task035e-blind-candidate-gate" not in result:
        raise BlindCampaignError("expensive argv lacks the blind candidate gate")
    if "--allow-swap" in result or "--worker" in result:
        raise BlindCampaignError("swap and direct worker launch are forbidden")
    if _one_option(result, "--run-kind") != "full-solve":
        raise BlindCampaignError("expensive blind stages require full-solve")
    if _one_option(result, "--degree") != "6":
        raise BlindCampaignError("formal blind stages require p6")
    if _one_option(result, "--h-nm") not in {"20", "20.0", "15", "15.0"}:
        raise BlindCampaignError("formal blind stages require Path A/B h")
    if _one_option(result, "--polarization-kind") != "s":
        raise BlindCampaignError("formal blind stages require S polarization")
    if _one_option(result, "--profile") != "default":
        raise BlindCampaignError("formal blind stages require default profile")
    if (
        _one_option(result, "--stage4-full3d-assembly-backend")
        != "assembly_time_variable_p_condensed"
    ):
        raise BlindCampaignError("expensive argv uses the wrong backend")
    if "--stage4-raw-tensor-cache" not in result:
        raise BlindCampaignError("formal blind runs require the tensor cache")
    _one_option(result, "--stage4-local-h-refinement-plan")
    _sha256(
        _one_option(
            result,
            "--stage4-local-h-refinement-plan-sha256",
        ),
        label="watchdog plan SHA-256",
    )
    source_sha = _source_sha(_one_option(result, "--verified-clean-sha"))
    if (
        expected_source_sha is not None
        and source_sha != _source_sha(expected_source_sha)
    ):
        raise CampaignIdentityDrift("watchdog source SHA differs")
    mpi_size = int(_one_option(result, "--mpi-size"))
    probe_values = _option_values(
        result,
        "--task035e-internal-probe-kind",
    )
    probe = probe_values[0] if len(probe_values) == 1 else None
    if len(probe_values) > 1:
        raise BlindCampaignError("internal probe kind is duplicated")
    if mpi_size == 2:
        raise BlindCampaignError("MPI2 is forbidden")
    if mpi_size == 1:
        if probe != "serial_mpi1":
            raise BlindCampaignError("MPI1 is restricted to serial_mpi1")
    elif mpi_size != FORMAL_MPI_SIZE or probe == "serial_mpi1":
        raise BlindCampaignError(
            "all non-serial-probe expensive stages require MPI8"
        )
    _trial_id(
        _one_option(result, "--task035e-blind-trial-id"),
        label="watchdog trial_id",
    )
    cycle = int(_one_option(result, "--task035e-blind-cycle-index"))
    if not 0 <= cycle < MAXIMUM_CYCLES:
        raise BlindCampaignError("watchdog cycle is outside [0, 5]")
    role = _one_option(
        result,
        "--task035e-blind-output-role",
    )
    if role not in {"current", "p-shadow", "h-shadow"}:
        raise BlindCampaignError("watchdog output role is not allowed")
    snapshot_paths = _option_values(
        result,
        "--task035e-current-snapshot-manifest",
    )
    snapshot_hashes = _option_values(
        result,
        "--task035e-current-snapshot-manifest-sha256",
    )
    action_paths = _option_values(
        result,
        "--task035e-transition-action",
    )
    action_hashes = _option_values(
        result,
        "--task035e-transition-action-sha256",
    )
    if len(snapshot_paths) != len(snapshot_hashes) or len(snapshot_paths) > 1:
        raise BlindCampaignError("watchdog snapshot path/hash scope differs")
    if len(action_paths) != len(action_hashes) or len(action_paths) > 1:
        raise BlindCampaignError("watchdog action path/hash scope differs")
    if snapshot_paths:
        if not Path(snapshot_paths[0]).is_absolute():
            raise BlindCampaignError("watchdog snapshot path must be absolute")
        _sha256(snapshot_hashes[0], label="watchdog snapshot SHA-256")
    if action_paths:
        if not Path(action_paths[0]).is_absolute():
            raise BlindCampaignError("watchdog action path must be absolute")
        _sha256(action_hashes[0], label="watchdog action SHA-256")
    initial_current = role == "current" and cycle == 0 and probe is None
    if initial_current:
        if snapshot_paths or action_paths:
            raise BlindCampaignError(
                "initial current argv accepts no snapshot or action"
            )
    elif probe is not None:
        if (
            role != "current"
            or len(snapshot_paths) != 1
            or action_paths
        ):
            raise BlindCampaignError(
                "internal probe argv requires current snapshot and no action"
            )
    elif len(snapshot_paths) != 1 or len(action_paths) != 1:
        raise BlindCampaignError(
            "noninitial/shadow argv requires snapshot and action"
        )
    _one_option(result, "--artifact-root")
    _one_option(result, "--run-dir")
    _one_option(result, "--record")
    return result


class SingleHeavyLock:
    """Nonblocking host-wide lock for exactly one expensive PDE."""

    def __init__(self, path: Path = DEFAULT_HEAVY_LOCK_PATH) -> None:
        self.path = Path(path)
        self._descriptor: int | None = None

    def __enter__(self) -> "SingleHeavyLock":
        if self.path.is_symlink():
            raise HeavyStageBusy("heavy-stage lock path must not be a symlink")
        with _private_umask():
            descriptor = os.open(
                self.path,
                os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
        try:
            fcntl.flock(
                descriptor,
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )
        except BlockingIOError as exc:
            os.close(descriptor)
            raise HeavyStageBusy(
                "another host process is running an expensive PDE"
            ) from exc
        self._descriptor = descriptor
        return self

    def __exit__(self, *_args: object) -> None:
        if self._descriptor is not None:
            fcntl.flock(self._descriptor, fcntl.LOCK_UN)
            os.close(self._descriptor)
            self._descriptor = None


class _CampaignRunLock(SingleHeavyLock):
    """Per-root orchestration lock; separate from the host-wide PDE lock."""


def _process_start_ticks(pid: int) -> str | None:
    try:
        fields = Path(f"/proc/{pid}/stat").read_text(
            encoding="ascii"
        ).split()
    except (OSError, UnicodeError):
        return None
    return fields[21] if len(fields) > 21 else None


@dataclass(frozen=True, slots=True)
class AttemptHandle:
    """Private attempt directory supplied to one stage implementation."""

    context: StageExecutionContext
    attempt_number: int
    attempt_dir: Path

    def write_artifact(
        self,
        name: str,
        value: Mapping[str, Any] | bytes,
    ) -> Path:
        if _ARTIFACT_NAME_RE.fullmatch(str(name)) is None:
            raise BlindCampaignError("artifact name is not a safe basename")
        output = self.attempt_dir / str(name)
        payload = (
            _canonical_bytes(value)
            if isinstance(value, Mapping)
            else bytes(value)
        )
        _atomic_private_write(output, payload)
        return output

    def record_process(
        self,
        pid: int,
        *,
        invocation_index: int,
        argv_sha256: str,
        linux_start_ticks: str | None = None,
    ) -> Path:
        if type(pid) is not int or pid <= 0:
            raise BlindCampaignError("recorded process PID must be positive")
        if type(invocation_index) is not int or invocation_index < 0:
            raise BlindCampaignError(
                "recorded invocation index must be nonnegative"
            )
        command_sha = _sha256(
            argv_sha256,
            label="recorded process argv SHA-256",
        )
        start_ticks = (
            _process_start_ticks(pid)
            if linux_start_ticks is None
            else str(linux_start_ticks)
        )
        if not start_ticks:
            raise BlindCampaignError(
                "recorded process requires Linux start ticks"
            )
        payload = {
            "schema_version": ATTEMPT_PROCESS_SCHEMA,
            "stage_id": self.context.stage.stage_id,
            "attempt_number": self.attempt_number,
            "invocation_index": invocation_index,
            "argv_sha256": command_sha,
            "pid": pid,
            "linux_start_ticks": start_ticks,
        }
        output = (
            self.attempt_dir
            / f"invocation-{invocation_index:03d}.process.json"
        )
        _write_outer(
            output,
            schema_version=ATTEMPT_PROCESS_SCHEMA,
            payload=payload,
        )
        return output


@dataclass(frozen=True, slots=True)
class CommandExecution:
    """Raw result supplied by an injected or subprocess command runner."""

    pid: int
    linux_start_ticks: str
    exit_code: int
    stdout_path: Path
    stderr_path: Path
    watchdog_record_path: Path | None


@dataclass(frozen=True, slots=True)
class CommandExecutionReceipt:
    """Validated immutable evidence for exactly one declared invocation."""

    invocation_index: int
    argv_sha256: str
    pid: int
    linux_start_ticks: str
    exit_code: int
    stdout_path: Path
    stdout_sha256: str
    stderr_path: Path
    stderr_sha256: str
    watchdog_record_path: Path | None
    watchdog_record_sha256: str | None
    receipt_path: Path
    receipt_file_sha256: str


class CommandRunner(Protocol):
    """Execute one argv without a shell and preserve its process identity."""

    def __call__(
        self,
        argv: tuple[str, ...],
        *,
        attempt: AttemptHandle,
        invocation_index: int,
        argv_sha256: str,
    ) -> CommandExecution: ...


class SubprocessCommandRunner:
    """Default ``shell=False`` runner used by formal campaign execution."""

    def __call__(
        self,
        argv: tuple[str, ...],
        *,
        attempt: AttemptHandle,
        invocation_index: int,
        argv_sha256: str,
    ) -> CommandExecution:
        stdout_path = (
            attempt.attempt_dir
            / f"invocation-{invocation_index:03d}.stdout"
        )
        stderr_path = (
            attempt.attempt_dir
            / f"invocation-{invocation_index:03d}.stderr"
        )
        for path in (stdout_path, stderr_path):
            if path.exists() or path.is_symlink():
                raise FileExistsError(
                    f"refusing to overwrite command stream: {path}"
                )
        record_path = Path(_one_option(argv, "--record"))
        try:
            record_path.resolve().relative_to(
                attempt.attempt_dir.resolve()
            )
        except ValueError as exc:
            raise CommandExecutionError(
                "watchdog record must be inside its attempt directory"
            ) from exc
        if record_path.exists() or record_path.is_symlink():
            raise FileExistsError(
                f"refusing to overwrite watchdog record: {record_path}"
            )
        stdout_descriptor = os.open(
            stdout_path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
        stderr_descriptor = os.open(
            stderr_path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
        try:
            with (
                os.fdopen(stdout_descriptor, "wb") as stdout_stream,
                os.fdopen(stderr_descriptor, "wb") as stderr_stream,
            ):
                process = subprocess.Popen(
                    argv,
                    shell=False,
                    cwd=Path(__file__).resolve().parents[1],
                    stdin=subprocess.DEVNULL,
                    stdout=stdout_stream,
                    stderr=stderr_stream,
                    close_fds=True,
                )
                start_ticks = _process_start_ticks(process.pid)
                if start_ticks is None:
                    process.kill()
                    process.wait()
                    raise CommandExecutionError(
                        "cannot capture watchdog Linux process identity"
                    )
                attempt.record_process(
                    process.pid,
                    invocation_index=invocation_index,
                    argv_sha256=argv_sha256,
                    linux_start_ticks=start_ticks,
                )
                exit_code = int(process.wait())
                stdout_stream.flush()
                stderr_stream.flush()
                os.fsync(stdout_stream.fileno())
                os.fsync(stderr_stream.fileno())
        except BaseException:
            try:
                os.close(stdout_descriptor)
            except OSError:
                pass
            try:
                os.close(stderr_descriptor)
            except OSError:
                pass
            raise
        return CommandExecution(
            pid=process.pid,
            linux_start_ticks=start_ticks,
            exit_code=exit_code,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            watchdog_record_path=(
                record_path if record_path.is_file() else None
            ),
        )


def _argv_sha256(argv: Sequence[str]) -> str:
    return hashlib.sha256(
        b"\0".join(str(item).encode("utf-8") for item in argv)
    ).hexdigest()


def _attempt_relative_file(
    attempt: AttemptHandle,
    path: Path,
    *,
    label: str,
) -> tuple[Path, str]:
    resolved = _require_private_file(path, label=label)
    try:
        relative = resolved.relative_to(attempt.attempt_dir.resolve())
    except ValueError as exc:
        raise CampaignEvidenceError(
            f"{label} must be inside its attempt directory"
        ) from exc
    return resolved, relative.as_posix()


def _write_command_execution_receipt(
    attempt: AttemptHandle,
    *,
    argv: tuple[str, ...],
    invocation_index: int,
    execution: CommandExecution,
) -> CommandExecutionReceipt:
    argv_sha = _argv_sha256(argv)
    if type(execution.pid) is not int or execution.pid <= 0:
        raise CampaignEvidenceError("command PID is invalid")
    if not str(execution.linux_start_ticks):
        raise CampaignEvidenceError("command Linux start ticks are missing")
    if type(execution.exit_code) is not int:
        raise CampaignEvidenceError("command exit code is invalid")
    process_path = (
        attempt.attempt_dir
        / f"invocation-{invocation_index:03d}.process.json"
    )
    process_payload = _load_outer(
        process_path,
        schema_version=ATTEMPT_PROCESS_SCHEMA,
        label="command process identity",
    )
    expected_process = {
        "schema_version": ATTEMPT_PROCESS_SCHEMA,
        "stage_id": attempt.context.stage.stage_id,
        "attempt_number": attempt.attempt_number,
        "invocation_index": invocation_index,
        "argv_sha256": argv_sha,
        "pid": execution.pid,
        "linux_start_ticks": str(execution.linux_start_ticks),
    }
    if process_payload != expected_process:
        raise CampaignEvidenceError(
            "command process identity differs from its execution"
        )
    stdout_path, stdout_relative = _attempt_relative_file(
        attempt,
        execution.stdout_path,
        label="command stdout",
    )
    stderr_path, stderr_relative = _attempt_relative_file(
        attempt,
        execution.stderr_path,
        label="command stderr",
    )
    expected_record = Path(_one_option(argv, "--record")).resolve()
    watchdog_path: Path | None = None
    watchdog_relative: str | None = None
    watchdog_sha: str | None = None
    watchdog_size: int | None = None
    if execution.watchdog_record_path is not None:
        watchdog_path, watchdog_relative = _attempt_relative_file(
            attempt,
            execution.watchdog_record_path,
            label="expected watchdog record",
        )
        if watchdog_path != expected_record:
            raise CampaignEvidenceError(
                "command runner returned a different watchdog record"
            )
        watchdog_sha = _file_sha256(watchdog_path)
        watchdog_size = watchdog_path.stat().st_size
    if execution.exit_code == 0 and watchdog_path is None:
        raise CampaignEvidenceError(
            "successful watchdog invocation has no expected record"
        )
    payload = {
        "schema_version": COMMAND_EXECUTION_RECEIPT_SCHEMA,
        "stage_id": attempt.context.stage.stage_id,
        "attempt_number": attempt.attempt_number,
        "invocation_index": invocation_index,
        "argv_sha256": argv_sha,
        "pid": execution.pid,
        "linux_start_ticks": str(execution.linux_start_ticks),
        "exit_code": execution.exit_code,
        "process_record": {
            "path": process_path.name,
            "sha256": _file_sha256(process_path),
        },
        "stdout": {
            "path": stdout_relative,
            "sha256": _file_sha256(stdout_path),
            "size_bytes": stdout_path.stat().st_size,
        },
        "stderr": {
            "path": stderr_relative,
            "sha256": _file_sha256(stderr_path),
            "size_bytes": stderr_path.stat().st_size,
        },
        "expected_watchdog_record": (
            None
            if watchdog_path is None
            else {
                "path": watchdog_relative,
                "sha256": watchdog_sha,
                "size_bytes": watchdog_size,
            }
        ),
    }
    receipt_path = (
        attempt.attempt_dir
        / f"invocation-{invocation_index:03d}.receipt.json"
    )
    _write_outer(
        receipt_path,
        schema_version=COMMAND_EXECUTION_RECEIPT_SCHEMA,
        payload=payload,
    )
    return CommandExecutionReceipt(
        invocation_index=invocation_index,
        argv_sha256=argv_sha,
        pid=execution.pid,
        linux_start_ticks=str(execution.linux_start_ticks),
        exit_code=execution.exit_code,
        stdout_path=stdout_path,
        stdout_sha256=str(payload["stdout"]["sha256"]),
        stderr_path=stderr_path,
        stderr_sha256=str(payload["stderr"]["sha256"]),
        watchdog_record_path=watchdog_path,
        watchdog_record_sha256=watchdog_sha,
        receipt_path=receipt_path,
        receipt_file_sha256=_file_sha256(receipt_path),
    )


def _load_command_execution_receipt(
    attempt_dir: Path,
    *,
    invocation_index: int,
    expected_file_sha256: str,
    expected_stage_id: str,
    expected_attempt_number: int,
) -> CommandExecutionReceipt:
    receipt_path = (
        attempt_dir / f"invocation-{invocation_index:03d}.receipt.json"
    )
    _require_private_file(
        receipt_path,
        label="command execution receipt",
        expected_sha256=expected_file_sha256,
    )
    payload = _load_outer(
        receipt_path,
        schema_version=COMMAND_EXECUTION_RECEIPT_SCHEMA,
        label="command execution receipt",
    )
    expected_keys = {
        "schema_version",
        "stage_id",
        "attempt_number",
        "invocation_index",
        "argv_sha256",
        "pid",
        "linux_start_ticks",
        "exit_code",
        "process_record",
        "stdout",
        "stderr",
        "expected_watchdog_record",
    }
    if set(payload) != expected_keys:
        raise CampaignEvidenceError(
            "command execution receipt schema differs"
        )
    if payload["invocation_index"] != invocation_index:
        raise CampaignEvidenceError(
            "command execution receipt order differs"
        )
    if (
        payload["stage_id"] != expected_stage_id
        or payload["attempt_number"] != expected_attempt_number
    ):
        raise CampaignEvidenceError(
            "command execution receipt stage identity differs"
        )
    argv_sha = _sha256(
        payload["argv_sha256"],
        label="command receipt argv SHA-256",
    )
    if (
        type(payload["pid"]) is not int
        or payload["pid"] <= 0
        or not isinstance(payload["linux_start_ticks"], str)
        or not payload["linux_start_ticks"]
        or type(payload["exit_code"]) is not int
    ):
        raise CampaignEvidenceError(
            "command execution process fields are invalid"
        )
    process_row = payload["process_record"]
    if not isinstance(process_row, Mapping) or set(process_row) != {
        "path",
        "sha256",
    }:
        raise CampaignEvidenceError("command process row differs")
    process_path = attempt_dir / str(process_row["path"])
    expected_process_path = (
        attempt_dir
        / f"invocation-{invocation_index:03d}.process.json"
    )
    if process_path.resolve() != expected_process_path.resolve():
        raise CampaignEvidenceError("command process record path differs")
    process_payload = _load_outer(
        _require_private_file(
            process_path,
            label="command process record",
            expected_sha256=str(process_row["sha256"]),
        ),
        schema_version=ATTEMPT_PROCESS_SCHEMA,
        label="command process record",
    )
    if (
        process_payload["invocation_index"] != invocation_index
        or process_payload["argv_sha256"] != argv_sha
        or process_payload["pid"] != payload["pid"]
        or process_payload["linux_start_ticks"]
        != payload["linux_start_ticks"]
    ):
        raise CampaignEvidenceError(
            "command execution and process identities differ"
        )

    def stream(
        name: str,
    ) -> tuple[Path, str]:
        row = payload[name]
        if not isinstance(row, Mapping) or set(row) != {
            "path",
            "sha256",
            "size_bytes",
        }:
            raise CampaignEvidenceError(f"command {name} row differs")
        path = _require_private_file(
            attempt_dir / str(row["path"]),
            label=f"command {name}",
            expected_sha256=str(row["sha256"]),
        )
        try:
            path.relative_to(attempt_dir.resolve())
        except ValueError as exc:
            raise CampaignEvidenceError(
                f"command {name} left its attempt directory"
            ) from exc
        if path.stat().st_size != row["size_bytes"]:
            raise CampaignEvidenceError(f"command {name} size differs")
        return path, str(row["sha256"])

    stdout_path, stdout_sha = stream("stdout")
    stderr_path, stderr_sha = stream("stderr")
    watchdog_row = payload["expected_watchdog_record"]
    watchdog_path: Path | None = None
    watchdog_sha: str | None = None
    if watchdog_row is not None:
        if not isinstance(watchdog_row, Mapping) or set(watchdog_row) != {
            "path",
            "sha256",
            "size_bytes",
        }:
            raise CampaignEvidenceError("watchdog record row differs")
        watchdog_path = _require_private_file(
            attempt_dir / str(watchdog_row["path"]),
            label="expected watchdog record",
            expected_sha256=str(watchdog_row["sha256"]),
        )
        try:
            watchdog_path.relative_to(attempt_dir.resolve())
        except ValueError as exc:
            raise CampaignEvidenceError(
                "watchdog record left its attempt directory"
            ) from exc
        if watchdog_path.stat().st_size != watchdog_row["size_bytes"]:
            raise CampaignEvidenceError("watchdog record size differs")
        watchdog_sha = str(watchdog_row["sha256"])
    if payload["exit_code"] == 0 and watchdog_path is None:
        raise CampaignEvidenceError(
            "successful command receipt lacks its watchdog record"
        )
    return CommandExecutionReceipt(
        invocation_index=invocation_index,
        argv_sha256=argv_sha,
        pid=int(payload["pid"]),
        linux_start_ticks=str(payload["linux_start_ticks"]),
        exit_code=int(payload["exit_code"]),
        stdout_path=stdout_path,
        stdout_sha256=stdout_sha,
        stderr_path=stderr_path,
        stderr_sha256=stderr_sha,
        watchdog_record_path=watchdog_path,
        watchdog_record_sha256=watchdog_sha,
        receipt_path=receipt_path,
        receipt_file_sha256=_file_sha256(receipt_path),
    )


def _campaign_payload_path(root: Path) -> Path:
    return root / "campaign.json"


def initialize_campaign(
    root: Path,
    identity: BlindCampaignIdentity,
) -> Path:
    """Create or revalidate one private immutable campaign identity."""

    identity.validate()
    resolved_root = _ensure_private_directory(
        Path(root),
        label="campaign root",
    )
    payload_path = _campaign_payload_path(resolved_root)
    expected = identity.payload()
    if payload_path.exists():
        observed = _load_outer(
            payload_path,
            schema_version=CAMPAIGN_SCHEMA,
            label="campaign identity",
        )
        if observed != expected:
            raise CampaignIdentityDrift(
                "campaign source/ABI/plan/trial/path identity differs"
            )
    else:
        _write_outer(
            payload_path,
            schema_version=CAMPAIGN_SCHEMA,
            payload=expected,
        )
    _ensure_private_directory(
        resolved_root / "receipts",
        label="campaign receipt directory",
    )
    _ensure_private_directory(
        resolved_root / "attempts",
        label="campaign attempt directory",
    )
    return resolved_root


def _receipt_path(root: Path, stage: CampaignStage) -> Path:
    return root / "receipts" / f"{stage.ordinal:04d}-{stage.stage_id}.json"


def _stage_attempt_root(root: Path, stage: CampaignStage) -> Path:
    return root / "attempts" / f"{stage.ordinal:04d}-{stage.stage_id}"


def _attempt_payload(
    context: StageExecutionContext,
    attempt_number: int,
) -> dict[str, Any]:
    stage = context.stage
    return {
        "schema_version": ATTEMPT_INTENT_SCHEMA,
        "stage_id": stage.stage_id,
        "stage_ordinal": stage.ordinal,
        "path_id": stage.path_id,
        "trial_id": context.trial_id,
        "cycle_index": stage.cycle_index,
        "stage_name": stage.stage_name,
        "heavy": stage.heavy,
        "source_sha": context.source_sha,
        "abi_sha256": context.abi_sha256,
        "input_plan_sha256": context.input_plan_sha256,
        "input_artifacts": [
            binding.payload() for binding in context.input_artifacts
        ],
        "attempt_number": attempt_number,
    }


def _process_is_same_alive(payload: Mapping[str, Any]) -> bool:
    if set(payload) != {
        "schema_version",
        "stage_id",
        "attempt_number",
        "invocation_index",
        "argv_sha256",
        "pid",
        "linux_start_ticks",
    }:
        raise CampaignEvidenceError("attempt process record schema differs")
    pid = payload["pid"]
    if type(pid) is not int or pid <= 0:
        raise CampaignEvidenceError("attempt process PID is invalid")
    expected_ticks = payload["linux_start_ticks"]
    if expected_ticks is not None and not isinstance(expected_ticks, str):
        raise CampaignEvidenceError("attempt process start identity is invalid")
    observed = _process_start_ticks(pid)
    return observed is not None and observed == expected_ticks


def _prepare_attempt(
    root: Path,
    context: StageExecutionContext,
) -> AttemptHandle:
    stage_root = _ensure_private_directory(
        _stage_attempt_root(root, context.stage),
        label="stage attempt directory",
    )
    existing = sorted(stage_root.glob("attempt-*"))
    for attempt_dir in existing:
        _ensure_private_directory(attempt_dir, label="attempt directory")
        intent_path = attempt_dir / "intent.json"
        intent = _load_outer(
            intent_path,
            schema_version=ATTEMPT_INTENT_SCHEMA,
            label="attempt intent",
        )
        expected_number = int(attempt_dir.name.split("-")[-1])
        if intent != _attempt_payload(context, expected_number):
            raise CampaignEvidenceError("prior attempt identity differs")
        interrupted_path = attempt_dir / "interrupted.json"
        if interrupted_path.exists():
            _load_outer(
                interrupted_path,
                schema_version=INTERRUPTED_ATTEMPT_SCHEMA,
                label="interrupted attempt",
            )
            continue
        process_paths = tuple(
            sorted(attempt_dir.glob("invocation-*.process.json"))
        )
        process_shas: list[str] = []
        for process_path in process_paths:
            process_payload = _load_outer(
                process_path,
                schema_version=ATTEMPT_PROCESS_SCHEMA,
                label="attempt process",
            )
            process_shas.append(_file_sha256(process_path))
            if _process_is_same_alive(process_payload):
                raise StageAlreadyRunning(
                    f"{context.stage.stage_id} has a live prior process"
                )
        interruption = {
            "schema_version": INTERRUPTED_ATTEMPT_SCHEMA,
            "status": "interrupted_preserved",
            "stage_id": context.stage.stage_id,
            "attempt_number": expected_number,
            "intent_file_sha256": _file_sha256(intent_path),
            "process_file_sha256s": process_shas,
            "reason": (
                "recorded_process_not_alive"
                if process_shas
                else "no_completed_stage_receipt"
            ),
        }
        _write_outer(
            interrupted_path,
            schema_version=INTERRUPTED_ATTEMPT_SCHEMA,
            payload=interruption,
        )

    attempt_number = len(existing) + 1
    attempt_dir = _ensure_private_directory(
        stage_root / f"attempt-{attempt_number:06d}",
        label="new attempt directory",
    )
    _write_outer(
        attempt_dir / "intent.json",
        schema_version=ATTEMPT_INTENT_SCHEMA,
        payload=_attempt_payload(context, attempt_number),
    )
    return AttemptHandle(
        context=context,
        attempt_number=attempt_number,
        attempt_dir=attempt_dir,
    )


def _relative_artifact(
    root: Path,
    attempt: AttemptHandle,
    binding: StageArtifactBinding,
) -> dict[str, Any]:
    resolved = binding.validate()
    try:
        resolved.relative_to(attempt.attempt_dir.resolve())
        relative = resolved.relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise CampaignEvidenceError(
            "stage artifact must be inside its attempt directory"
        ) from exc
    return {
        "role": binding.role,
        "path": relative,
        "sha256": binding.sha256,
        "size_bytes": binding.size_bytes,
    }


def _normalized_result(
    stage: CampaignStage,
    result: StageResult,
) -> StageResult:
    if (
        stage.stage_name == "cycle_advance"
        and result.lane_decision == "freeze_ready"
        and (
            result.freeze_requested is not True
            or result.p6_saturation != "verified"
            or result.h_level3_saturation != "verified"
        )
    ):
        if result.freeze_requested is not True:
            classification = "freeze_blocked_freeze_request_contract"
        elif result.p6_saturation != "verified":
            classification = "freeze_blocked_p6_saturation_unknown"
        else:
            classification = (
                "freeze_blocked_h_level3_saturation_unknown"
            )
        return StageResult(
            status="controlled_negative",
            classification=classification,
            input_plan_sha256=result.input_plan_sha256,
            artifacts=result.artifacts,
            command_receipt_file_sha256s=(
                result.command_receipt_file_sha256s
            ),
            next_plan_sha256=result.next_plan_sha256,
            lane_decision="controlled_negative",
            freeze_requested=True,
            p6_saturation=result.p6_saturation,
            h_level3_saturation=result.h_level3_saturation,
        )
    return result


def _publish_receipt(
    root: Path,
    context: StageExecutionContext,
    attempt: AttemptHandle,
    prepared: PreparedStage,
    command_receipts: tuple[CommandExecutionReceipt, ...],
    raw_result: StageResult,
) -> Mapping[str, Any]:
    stage = context.stage
    result = _normalized_result(stage, raw_result)
    if result.input_plan_sha256 != context.input_plan_sha256:
        raise CampaignIdentityDrift("stage executed a different plan")
    if result.status == "controlled_negative":
        lane_decision = "controlled_negative"
    else:
        lane_decision = result.lane_decision
    if (
        result.status == "completed"
        and stage.stage_name != "cycle_advance"
        and lane_decision != "continue"
    ):
        raise BlindCampaignError(
            "only cycle_advance may freeze or terminate a lane"
        )
    if stage.stage_name == "transition_or_pkeep":
        if result.next_plan_sha256 is None:
            raise BlindCampaignError(
                "transition_or_pkeep must bind its next plan SHA-256"
            )
        output_plan = result.next_plan_sha256
        next_plan_bindings = tuple(
            binding
            for binding in result.artifacts
            if binding.role == "current_plan"
        )
        if (
            len(next_plan_bindings) != 1
            or next_plan_bindings[0].sha256 != output_plan
        ):
            raise CampaignEvidenceError(
                "transition must publish its next plan as current_plan"
            )
    else:
        if result.next_plan_sha256 not in {
            None,
            context.input_plan_sha256,
        }:
            raise BlindCampaignError(
                "only transition_or_pkeep may change the plan"
            )
        output_plan = context.input_plan_sha256
    artifacts = [
        _relative_artifact(root, attempt, binding)
        for binding in result.artifacts
    ]
    command_hashes = [
        _argv_sha256(argv) for argv in prepared.command_argvs
    ]
    if tuple(receipt.argv_sha256 for receipt in command_receipts) != tuple(
        command_hashes
    ):
        raise CampaignEvidenceError(
            "command execution receipts differ from declared argv order"
        )
    command_rows = [
        {
            "invocation_index": receipt.invocation_index,
            "argv_sha256": receipt.argv_sha256,
            "receipt_path": (
                receipt.receipt_path.relative_to(root).as_posix()
            ),
            "receipt_file_sha256": receipt.receipt_file_sha256,
            "exit_code": receipt.exit_code,
            "stdout_sha256": receipt.stdout_sha256,
            "stderr_sha256": receipt.stderr_sha256,
            "expected_watchdog_record_sha256": (
                receipt.watchdog_record_sha256
            ),
        }
        for receipt in command_receipts
    ]
    payload = {
        "schema_version": STAGE_RECEIPT_SCHEMA,
        "status": result.status,
        "classification": result.classification,
        "stage_id": stage.stage_id,
        "stage_ordinal": stage.ordinal,
        "path_id": stage.path_id,
        "trial_id": context.trial_id,
        "cycle_index": stage.cycle_index,
        "stage_name": stage.stage_name,
        "heavy": stage.heavy,
        "source_sha": context.source_sha,
        "abi_sha256": context.abi_sha256,
        "input_plan_sha256": context.input_plan_sha256,
        "input_artifacts": [
            binding.payload() for binding in context.input_artifacts
        ],
        "output_plan_sha256": output_plan,
        "attempt_number": attempt.attempt_number,
        "attempt_dir": attempt.attempt_dir.relative_to(root).as_posix(),
        "command_argv_sha256s": command_hashes,
        "command_execution_receipts": command_rows,
        "artifacts": artifacts,
        "lane_decision": lane_decision,
        "freeze_requested": result.freeze_requested,
        "p6_saturation": result.p6_saturation,
        "h_level3_saturation": result.h_level3_saturation,
        "ordinary_default_changed": False,
    }
    _write_outer(
        _receipt_path(root, stage),
        schema_version=STAGE_RECEIPT_SCHEMA,
        payload=payload,
    )
    return payload


_RECEIPT_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "classification",
        "stage_id",
        "stage_ordinal",
        "path_id",
        "trial_id",
        "cycle_index",
        "stage_name",
        "heavy",
        "source_sha",
        "abi_sha256",
        "input_plan_sha256",
        "input_artifacts",
        "output_plan_sha256",
        "attempt_number",
        "attempt_dir",
        "command_argv_sha256s",
        "command_execution_receipts",
        "artifacts",
        "lane_decision",
        "freeze_requested",
        "p6_saturation",
        "h_level3_saturation",
        "ordinary_default_changed",
    }
)


def _revalidate_receipt(
    root: Path,
    context: StageExecutionContext,
) -> Mapping[str, Any]:
    stage = context.stage
    payload = _load_outer(
        _receipt_path(root, stage),
        schema_version=STAGE_RECEIPT_SCHEMA,
        label="stage receipt",
    )
    if set(payload) != _RECEIPT_KEYS:
        raise CampaignEvidenceError("stage receipt closed schema differs")
    expected_identity = {
        "schema_version": STAGE_RECEIPT_SCHEMA,
        "stage_id": stage.stage_id,
        "stage_ordinal": stage.ordinal,
        "path_id": stage.path_id,
        "trial_id": context.trial_id,
        "cycle_index": stage.cycle_index,
        "stage_name": stage.stage_name,
        "heavy": stage.heavy,
        "source_sha": context.source_sha,
        "abi_sha256": context.abi_sha256,
        "input_plan_sha256": context.input_plan_sha256,
        "input_artifacts": [
            binding.payload() for binding in context.input_artifacts
        ],
        "ordinary_default_changed": False,
    }
    if any(payload[key] != value for key, value in expected_identity.items()):
        raise CampaignIdentityDrift("completed stage identity differs")
    if payload["status"] not in _ALLOWED_RESULT_STATUSES:
        raise CampaignEvidenceError("stage receipt status is invalid")
    _classification(payload["classification"])
    output_plan = _sha256(
        payload["output_plan_sha256"],
        label="stage receipt output plan SHA-256",
    )
    if (
        stage.stage_name != "transition_or_pkeep"
        and output_plan != context.input_plan_sha256
    ):
        raise CampaignEvidenceError("non-transition receipt changed the plan")
    if (
        type(payload["attempt_number"]) is not int
        or payload["attempt_number"] < 1
    ):
        raise CampaignEvidenceError("stage receipt attempt number is invalid")
    attempt_dir = root / str(payload["attempt_dir"])
    expected_attempt = (
        _stage_attempt_root(root, stage)
        / f"attempt-{payload['attempt_number']:06d}"
    )
    if attempt_dir.resolve() != expected_attempt.resolve():
        raise CampaignEvidenceError("stage receipt attempt path differs")
    _ensure_private_directory(attempt_dir, label="completed attempt directory")
    intent = _load_outer(
        attempt_dir / "intent.json",
        schema_version=ATTEMPT_INTENT_SCHEMA,
        label="completed attempt intent",
    )
    if intent != _attempt_payload(context, payload["attempt_number"]):
        raise CampaignEvidenceError("completed attempt intent differs")
    command_hashes = payload["command_argv_sha256s"]
    if not isinstance(command_hashes, list):
        raise CampaignEvidenceError(
            "stage command SHA-256 inventory must be an array"
        )
    for index, command_sha in enumerate(command_hashes):
        _sha256(
            command_sha,
            label=f"completed expensive argv {index} SHA-256",
        )
    command_rows = payload["command_execution_receipts"]
    if (
        not isinstance(command_rows, list)
        or len(command_rows) != len(command_hashes)
    ):
        raise CampaignEvidenceError(
            "command execution receipt inventory differs"
        )
    loaded_command_receipts: list[CommandExecutionReceipt] = []
    for index, row in enumerate(command_rows):
        if not isinstance(row, Mapping) or set(row) != {
            "invocation_index",
            "argv_sha256",
            "receipt_path",
            "receipt_file_sha256",
            "exit_code",
            "stdout_sha256",
            "stderr_sha256",
            "expected_watchdog_record_sha256",
        }:
            raise CampaignEvidenceError(
                "command execution receipt row schema differs"
            )
        if (
            row["invocation_index"] != index
            or row["argv_sha256"] != command_hashes[index]
        ):
            raise CampaignEvidenceError(
                "command execution receipt order differs"
            )
        receipt_path = root / str(row["receipt_path"])
        expected_receipt_path = (
            attempt_dir / f"invocation-{index:03d}.receipt.json"
        )
        if receipt_path.resolve() != expected_receipt_path.resolve():
            raise CampaignEvidenceError(
                "command execution receipt path differs"
            )
        loaded = _load_command_execution_receipt(
            attempt_dir,
            invocation_index=index,
            expected_file_sha256=str(row["receipt_file_sha256"]),
            expected_stage_id=stage.stage_id,
            expected_attempt_number=int(payload["attempt_number"]),
        )
        if (
            loaded.argv_sha256 != row["argv_sha256"]
            or loaded.exit_code != row["exit_code"]
            or loaded.exit_code != 0
            or loaded.stdout_sha256 != row["stdout_sha256"]
            or loaded.stderr_sha256 != row["stderr_sha256"]
            or loaded.watchdog_record_sha256
            != row["expected_watchdog_record_sha256"]
        ):
            raise CampaignEvidenceError(
                "command execution receipt summary differs"
            )
        loaded_command_receipts.append(loaded)
    if (
        stage.heavy
        and not command_hashes
        and stage.stage_name != "internal_gate_deferred_or_final"
    ):
        raise CampaignEvidenceError(
            "expensive stage receipt has no command credit"
        )
    if not stage.heavy and command_hashes:
        raise CampaignEvidenceError("light-stage receipt carries command credit")
    artifacts = payload["artifacts"]
    if not isinstance(artifacts, list) or not artifacts:
        raise CampaignEvidenceError("stage receipt has no artifacts")
    for row in artifacts:
        if not isinstance(row, Mapping) or set(row) != {
            "role",
            "path",
            "sha256",
            "size_bytes",
        }:
            raise CampaignEvidenceError("stage artifact row schema differs")
        if _ARTIFACT_ROLE_RE.fullmatch(str(row["role"])) is None:
            raise CampaignEvidenceError("stage artifact role is invalid")
        artifact = root / str(row["path"])
        resolved = _require_private_file(
            artifact,
            label="completed stage artifact",
            expected_sha256=str(row["sha256"]),
        )
        try:
            resolved.relative_to(attempt_dir.resolve())
        except ValueError as exc:
            raise CampaignEvidenceError(
                "completed artifact left its attempt directory"
            ) from exc
        if (
            type(row["size_bytes"]) is not int
            or row["size_bytes"] < 0
            or resolved.stat().st_size != row["size_bytes"]
        ):
            raise CampaignEvidenceError("completed artifact size differs")
    roles = [str(row["role"]) for row in artifacts]
    if len(set(roles)) != len(roles):
        raise CampaignEvidenceError(
            "stage artifact receipt roles are duplicated"
        )
    if payload["lane_decision"] not in _ALLOWED_LANE_DECISIONS:
        raise CampaignEvidenceError("receipt lane decision is invalid")
    if payload["p6_saturation"] not in _ALLOWED_SATURATION_STATES:
        raise CampaignEvidenceError("receipt saturation state is invalid")
    if payload["h_level3_saturation"] not in _ALLOWED_SATURATION_STATES:
        raise CampaignEvidenceError(
            "receipt level3 h saturation state is invalid"
        )
    if type(payload["freeze_requested"]) is not bool:
        raise CampaignEvidenceError("receipt freeze flag is invalid")
    if (
        payload["status"] == "controlled_negative"
        and payload["lane_decision"] != "controlled_negative"
    ):
        raise CampaignEvidenceError(
            "controlled-negative receipt must terminate its lane"
        )
    if (
        payload["status"] == "completed"
        and stage.stage_name != "cycle_advance"
        and payload["lane_decision"] != "continue"
    ):
        raise CampaignEvidenceError(
            "non-cycle receipt cannot terminate or freeze a lane"
        )
    if (
        payload["status"] == "completed"
        and payload["lane_decision"] == "freeze_ready"
        and (
            stage.stage_name != "cycle_advance"
            or payload["freeze_requested"] is not True
            or payload["p6_saturation"] != "verified"
            or payload["h_level3_saturation"] != "verified"
        )
    ):
        raise CampaignEvidenceError(
            "freeze receipt lacks verified p6 and level3 h saturation"
        )
    return payload


def _verify_live_identity(
    identity: BlindCampaignIdentity,
    *,
    source_sha_provider: Callable[[], str],
    abi_sha256_provider: Callable[[], str],
) -> None:
    observed_source = _source_sha(source_sha_provider())
    observed_abi = _sha256(
        abi_sha256_provider(),
        label="live ABI SHA-256",
    )
    if observed_source != identity.source_sha:
        raise CampaignIdentityDrift("source SHA drifted during campaign")
    if observed_abi != identity.abi_sha256:
        raise CampaignIdentityDrift("ABI drifted during campaign")
    identity.validate()


def _seed_path_artifacts(
    path: BlindPathIdentity,
) -> dict[str, StageArtifactBinding]:
    return {
        binding.role: binding
        for binding in (
            StageArtifactBinding.from_file(
                "current_plan",
                path.validate_plan(),
            ),
            StageArtifactBinding.from_file(
                "initial_space_authority",
                path.validate_initial_space_authority(),
            ),
            StageArtifactBinding.from_file(
                "qualified_solver_config",
                path.validate_qualified_solver_config(),
            ),
        )
    }


def _receipt_artifact_bindings(
    root: Path,
    payload: Mapping[str, Any],
) -> tuple[StageArtifactBinding, ...]:
    rows = payload["artifacts"]
    if not isinstance(rows, list):
        raise CampaignEvidenceError("receipt artifacts must be an array")
    return tuple(
        StageArtifactBinding(
            role=str(row["role"]),
            path=root / str(row["path"]),
            sha256=str(row["sha256"]),
            size_bytes=int(row["size_bytes"]),
        )
        for row in rows
    )


def _execute_declared_commands(
    prepared: PreparedStage,
    *,
    attempt: AttemptHandle,
    command_runner: CommandRunner,
) -> tuple[CommandExecutionReceipt, ...]:
    receipts: list[CommandExecutionReceipt] = []
    for invocation_index, argv in enumerate(prepared.command_argvs):
        argv_sha = _argv_sha256(argv)
        execution = command_runner(
            argv,
            attempt=attempt,
            invocation_index=invocation_index,
            argv_sha256=argv_sha,
        )
        if not isinstance(execution, CommandExecution):
            raise CommandExecutionError(
                "command runner returned an invalid execution result"
            )
        receipt = _write_command_execution_receipt(
            attempt,
            argv=argv,
            invocation_index=invocation_index,
            execution=execution,
        )
        receipts.append(receipt)
        if receipt.exit_code != 0:
            raise CommandExecutionError(
                "watchdog invocation "
                f"{invocation_index} exited with {receipt.exit_code}"
            )
    return tuple(receipts)


def run_campaign(
    root: Path,
    identity: BlindCampaignIdentity,
    *,
    prepare_stage: StagePreparer,
    source_sha_provider: Callable[[], str],
    abi_sha256_provider: Callable[[], str],
    heavy_lock_path: Path = DEFAULT_HEAVY_LOCK_PATH,
    maximum_new_stages: int | None = None,
    command_runner: CommandRunner | None = None,
) -> Mapping[str, Any]:
    """Resume or advance a campaign from validated immutable receipts."""

    if maximum_new_stages is not None and (
        type(maximum_new_stages) is not int or maximum_new_stages < 0
    ):
        raise BlindCampaignError("maximum_new_stages must be nonnegative")
    resolved_root = initialize_campaign(root, identity)
    run_lock_path = resolved_root / ".campaign-run.lock"
    stages = build_campaign_stage_dag(identity)
    executed: list[str] = []
    reused: list[str] = []
    lane_status: dict[str, str] = {}
    terminal_artifacts: dict[
        str,
        dict[str, StageArtifactBinding],
    ] = {}
    terminal_plans: dict[str, str] = {}
    finalization_status = "not_run_lane_not_ready"
    new_count = 0
    runner = (
        SubprocessCommandRunner()
        if command_runner is None
        else command_runner
    )

    with _CampaignRunLock(run_lock_path):
        _verify_live_identity(
            identity,
            source_sha_provider=source_sha_provider,
            abi_sha256_provider=abi_sha256_provider,
        )
        for path in identity.paths:
            current_plan = path.initial_plan_sha256
            available_artifacts = _seed_path_artifacts(path)
            terminal = False
            lane_status[path.path_id] = "in_progress"
            path_stages = tuple(
                stage for stage in stages if stage.path_id == path.path_id
            )
            for stage in path_stages:
                if terminal:
                    break
                context = StageExecutionContext(
                    campaign_root=resolved_root,
                    stage=stage,
                    source_sha=identity.source_sha,
                    abi_sha256=identity.abi_sha256,
                    trial_id=path.trial_id,
                    nominal_h_nm=path.nominal_h_nm,
                    input_plan_sha256=current_plan,
                    input_artifacts=tuple(
                        available_artifacts[role]
                        for role in sorted(available_artifacts)
                    ),
                )
                receipt_path = _receipt_path(resolved_root, stage)
                if receipt_path.exists():
                    receipt = _revalidate_receipt(resolved_root, context)
                    reused.append(stage.stage_id)
                else:
                    if (
                        maximum_new_stages is not None
                        and new_count >= maximum_new_stages
                    ):
                        lane_status[path.path_id] = "partial"
                        return {
                            "schema_version": CAMPAIGN_REPORT_SCHEMA,
                            "status": "partial",
                            "source_sha": identity.source_sha,
                            "abi_sha256": identity.abi_sha256,
                            "executed_stage_ids": executed,
                            "reused_stage_ids": reused,
                            "lane_status": lane_status,
                            "finalization_status": (
                                "not_run_lane_not_ready"
                            ),
                            "next_stage_id": stage.stage_id,
                            "path_a_completed_before_path_b": False,
                        }
                    _verify_live_identity(
                        identity,
                        source_sha_provider=source_sha_provider,
                        abi_sha256_provider=abi_sha256_provider,
                    )
                    attempt = _prepare_attempt(resolved_root, context)
                    prepared = prepare_stage(context, attempt)
                    if not isinstance(prepared, PreparedStage):
                        raise BlindCampaignError(
                            "stage preparer did not return PreparedStage"
                        )
                    command_argvs = prepared.command_argvs
                    if stage.heavy:
                        if (
                            not command_argvs
                            and stage.stage_name
                            != "internal_gate_deferred_or_final"
                        ):
                            raise BlindCampaignError(
                                "expensive stage lacks watchdog argv"
                            )
                        for command_argv in command_argvs:
                            validate_watchdog_argv(
                                command_argv,
                                expected_source_sha=identity.source_sha,
                            )
                        if stage.stage_name == (
                            "internal_gate_deferred_or_final"
                        ):
                            observed_probes = tuple(
                                _one_option(
                                    command_argv,
                                    "--task035e-internal-probe-kind",
                                )
                                for command_argv in command_argvs
                            )
                            if observed_probes not in {
                                (),
                                FINAL_INTERNAL_PROBE_ORDER,
                            }:
                                raise BlindCampaignError(
                                    "final internal probes must be the closed "
                                    "ordered four-probe inventory"
                                )
                        with SingleHeavyLock(heavy_lock_path):
                            command_receipts = _execute_declared_commands(
                                prepared,
                                attempt=attempt,
                                command_runner=runner,
                            )
                            raw_result = prepared.execute(
                                attempt,
                                command_receipts,
                            )
                    else:
                        if command_argvs:
                            raise BlindCampaignError(
                                "light stage must not carry an expensive argv"
                            )
                        command_receipts = ()
                        raw_result = prepared.execute(
                            attempt,
                            command_receipts,
                        )
                    _verify_live_identity(
                        identity,
                        source_sha_provider=source_sha_provider,
                        abi_sha256_provider=abi_sha256_provider,
                    )
                    if not isinstance(raw_result, StageResult):
                        raise BlindCampaignError(
                            "stage implementation did not return StageResult"
                        )
                    expected_command_receipt_shas = tuple(
                        receipt.receipt_file_sha256
                        for receipt in command_receipts
                    )
                    if (
                        raw_result.command_receipt_file_sha256s
                        != expected_command_receipt_shas
                    ):
                        raise CampaignEvidenceError(
                            "stage finalizer did not bind every command "
                            "execution receipt in order"
                        )
                    receipt = _publish_receipt(
                        resolved_root,
                        context,
                        attempt,
                        prepared,
                        command_receipts,
                        raw_result,
                    )
                    executed.append(stage.stage_id)
                    new_count += 1

                for binding in _receipt_artifact_bindings(
                    resolved_root,
                    receipt,
                ):
                    available_artifacts[binding.role] = binding
                current_plan = str(receipt["output_plan_sha256"])
                current_plan_binding = available_artifacts.get(
                    "current_plan"
                )
                if (
                    current_plan_binding is None
                    or current_plan_binding.sha256 != current_plan
                ):
                    raise CampaignEvidenceError(
                        "current_plan artifact does not bind output plan"
                    )
                if receipt["status"] == "controlled_negative":
                    terminal = True
                    lane_status[path.path_id] = "controlled_negative"
                elif (
                    stage.stage_name == "cycle_advance"
                    and receipt["lane_decision"] == "freeze_ready"
                ):
                    if (
                        receipt["freeze_requested"] is not True
                        or receipt["p6_saturation"] != "verified"
                        or receipt["h_level3_saturation"] != "verified"
                    ):
                        raise CampaignEvidenceError(
                            "freeze receipt bypassed p6 or level3 h "
                            "saturation Gate"
                        )
                    terminal = True
                    lane_status[path.path_id] = "freeze_ready"
            if not terminal:
                lane_status[path.path_id] = "cycle_limit_exhausted"
            terminal_artifacts[path.path_id] = dict(available_artifacts)
            terminal_plans[path.path_id] = current_plan
            if path.path_id == "A" and lane_status["A"] == "partial":
                break

        if lane_status == {"A": "freeze_ready", "B": "freeze_ready"}:
            final_available: dict[str, StageArtifactBinding] = {}
            for path_id in ("A", "B"):
                prefix = f"path_{path_id.lower()}_"
                for role, binding in terminal_artifacts[path_id].items():
                    final_available[prefix + role] = (
                        StageArtifactBinding(
                            role=prefix + role,
                            path=binding.path,
                            sha256=binding.sha256,
                            size_bytes=binding.size_bytes,
                        )
                    )
            final_plan_sha = _json_sha256(
                {
                    "path_a_plan_sha256": terminal_plans["A"],
                    "path_b_plan_sha256": terminal_plans["B"],
                }
            )
            finalization_status = "in_progress"
            final_stages = tuple(
                stage for stage in stages if stage.path_id == "FINAL"
            )
            for stage in final_stages:
                context = StageExecutionContext(
                    campaign_root=resolved_root,
                    stage=stage,
                    source_sha=identity.source_sha,
                    abi_sha256=identity.abi_sha256,
                    trial_id="task035e-blind-two-start-final",
                    nominal_h_nm=0.0,
                    input_plan_sha256=final_plan_sha,
                    input_artifacts=tuple(
                        final_available[role]
                        for role in sorted(final_available)
                    ),
                )
                receipt_path = _receipt_path(resolved_root, stage)
                if receipt_path.exists():
                    receipt = _revalidate_receipt(
                        resolved_root,
                        context,
                    )
                    reused.append(stage.stage_id)
                else:
                    if (
                        maximum_new_stages is not None
                        and new_count >= maximum_new_stages
                    ):
                        return {
                            "schema_version": CAMPAIGN_REPORT_SCHEMA,
                            "status": "partial",
                            "source_sha": identity.source_sha,
                            "abi_sha256": identity.abi_sha256,
                            "executed_stage_ids": executed,
                            "reused_stage_ids": reused,
                            "lane_status": lane_status,
                            "finalization_status": "partial",
                            "next_stage_id": stage.stage_id,
                            "path_a_completed_before_path_b": True,
                        }
                    _verify_live_identity(
                        identity,
                        source_sha_provider=source_sha_provider,
                        abi_sha256_provider=abi_sha256_provider,
                    )
                    attempt = _prepare_attempt(resolved_root, context)
                    prepared = prepare_stage(context, attempt)
                    if not isinstance(prepared, PreparedStage):
                        raise BlindCampaignError(
                            "final stage preparer did not return "
                            "PreparedStage"
                        )
                    if prepared.command_argvs:
                        raise BlindCampaignError(
                            "campaign finalization stages must be light"
                        )
                    command_receipts: tuple[
                        CommandExecutionReceipt,
                        ...,
                    ] = ()
                    raw_result = prepared.execute(
                        attempt,
                        command_receipts,
                    )
                    if not isinstance(raw_result, StageResult):
                        raise BlindCampaignError(
                            "final stage returned a non-StageResult"
                        )
                    if raw_result.command_receipt_file_sha256s:
                        raise CampaignEvidenceError(
                            "light final stage claimed command receipts"
                        )
                    receipt = _publish_receipt(
                        resolved_root,
                        context,
                        attempt,
                        prepared,
                        command_receipts,
                        raw_result,
                    )
                    executed.append(stage.stage_id)
                    new_count += 1
                for binding in _receipt_artifact_bindings(
                    resolved_root,
                    receipt,
                ):
                    final_available[binding.role] = binding
                if receipt["status"] == "controlled_negative":
                    finalization_status = "controlled_negative"
                    break
                if stage.stage_name == "two_start_comparison":
                    if "two_start_comparison" not in final_available:
                        raise CampaignEvidenceError(
                            "two-start comparison did not publish its Gate"
                        )
                elif stage.stage_name == "candidate_freeze":
                    if "candidate_freeze" not in final_available:
                        raise CampaignEvidenceError(
                            "candidate freeze artifact is missing"
                        )
                    finalization_status = "frozen"

    return {
        "schema_version": CAMPAIGN_REPORT_SCHEMA,
        "status": "completed",
        "source_sha": identity.source_sha,
        "abi_sha256": identity.abi_sha256,
        "executed_stage_ids": executed,
        "reused_stage_ids": reused,
        "lane_status": lane_status,
        "finalization_status": finalization_status,
        "next_stage_id": None,
        "path_a_completed_before_path_b": (
            "A" in lane_status
            and "B" in lane_status
            and lane_status["A"] != "in_progress"
        ),
    }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-root", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--abi-sha256", required=True)
    parser.add_argument("--path-a-plan", type=Path, required=True)
    parser.add_argument("--path-a-plan-sha256", required=True)
    parser.add_argument(
        "--path-a-initial-space-authority",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--path-a-initial-space-authority-sha256",
        required=True,
    )
    parser.add_argument(
        "--path-a-qualified-solver-config",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--path-a-qualified-solver-config-sha256",
        required=True,
    )
    parser.add_argument(
        "--path-a-trial-id",
        default="task035e-blind-path-a",
    )
    parser.add_argument("--path-b-plan", type=Path, required=True)
    parser.add_argument("--path-b-plan-sha256", required=True)
    parser.add_argument(
        "--path-b-initial-space-authority",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--path-b-initial-space-authority-sha256",
        required=True,
    )
    parser.add_argument(
        "--path-b-qualified-solver-config",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--path-b-qualified-solver-config-sha256",
        required=True,
    )
    parser.add_argument(
        "--path-b-trial-id",
        default="task035e-blind-path-b",
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Freeze identity and print the DAG; never execute a stage.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    if not args.plan_only:
        print(
            json.dumps(
                {
                    "schema_version": CAMPAIGN_REPORT_SCHEMA,
                    "status": "failed",
                    "error": (
                        "this core CLI is plan-only; inject qualified stage "
                        "implementations through run_campaign"
                    ),
                },
                sort_keys=True,
            )
        )
        return 2
    try:
        identity = BlindCampaignIdentity(
            source_sha=args.source_sha,
            abi_sha256=args.abi_sha256,
            paths=(
                BlindPathIdentity(
                    path_id="A",
                    trial_id=args.path_a_trial_id,
                    nominal_h_nm=20.0,
                    initial_plan_path=args.path_a_plan,
                    initial_plan_sha256=args.path_a_plan_sha256,
                    initial_space_authority_path=(
                        args.path_a_initial_space_authority
                    ),
                    initial_space_authority_sha256=(
                        args.path_a_initial_space_authority_sha256
                    ),
                    qualified_solver_config_path=(
                        args.path_a_qualified_solver_config
                    ),
                    qualified_solver_config_sha256=(
                        args.path_a_qualified_solver_config_sha256
                    ),
                ),
                BlindPathIdentity(
                    path_id="B",
                    trial_id=args.path_b_trial_id,
                    nominal_h_nm=15.0,
                    initial_plan_path=args.path_b_plan,
                    initial_plan_sha256=args.path_b_plan_sha256,
                    initial_space_authority_path=(
                        args.path_b_initial_space_authority
                    ),
                    initial_space_authority_sha256=(
                        args.path_b_initial_space_authority_sha256
                    ),
                    qualified_solver_config_path=(
                        args.path_b_qualified_solver_config
                    ),
                    qualified_solver_config_sha256=(
                        args.path_b_qualified_solver_config_sha256
                    ),
                ),
            ),
        )
        root = initialize_campaign(args.campaign_root, identity)
        stages = build_campaign_stage_dag(identity)
    except (BlindCampaignError, FileExistsError, OSError) as error:
        print(
            json.dumps(
                {
                    "schema_version": CAMPAIGN_REPORT_SCHEMA,
                    "status": "failed",
                    "error": str(error),
                },
                sort_keys=True,
            )
        )
        return 2
    print(
        json.dumps(
            {
                "schema_version": CAMPAIGN_REPORT_SCHEMA,
                "status": "planned",
                "campaign_root": str(root),
                "source_sha": identity.source_sha,
                "abi_sha256": identity.abi_sha256,
                "stage_count": len(stages),
                "stage_ids": [stage.stage_id for stage in stages],
                "path_a_completed_before_path_b": True,
                "formal_mpi_size": FORMAL_MPI_SIZE,
                "ordinary_default_changed": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ATTEMPT_INTENT_SCHEMA",
    "ATTEMPT_PROCESS_SCHEMA",
    "BlindCampaignError",
    "BlindCampaignIdentity",
    "BlindPathIdentity",
    "CAMPAIGN_REPORT_SCHEMA",
    "CAMPAIGN_SCHEMA",
    "CampaignEvidenceError",
    "CampaignIdentityDrift",
    "CampaignStage",
    "COMMAND_EXECUTION_RECEIPT_SCHEMA",
    "CommandExecution",
    "CommandExecutionError",
    "CommandExecutionReceipt",
    "CommandRunner",
    "DEFAULT_HEAVY_LOCK_PATH",
    "FORMAL_MPI_SIZE",
    "FINAL_INTERNAL_PROBE_ORDER",
    "HeavyStageBusy",
    "INTERRUPTED_ATTEMPT_SCHEMA",
    "MAXIMUM_CYCLES",
    "PreparedStage",
    "STAGE_RECEIPT_SCHEMA",
    "SingleHeavyLock",
    "StageAlreadyRunning",
    "StageArtifactBinding",
    "StageExecutionContext",
    "StageResult",
    "SubprocessCommandRunner",
    "WatchdogLaunchSpec",
    "build_campaign_stage_dag",
    "build_watchdog_argv",
    "initialize_campaign",
    "main",
    "run_campaign",
    "validate_watchdog_argv",
]
