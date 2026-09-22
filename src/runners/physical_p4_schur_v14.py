"""Task39extra V14 workers for the fresh p4/fullspace Schur comparison.

Q1 and Q2 are deliberately separate worker stages.  Each worker builds the
same p6/p4 mesh, mode inventory and three hash-bound p4 right-hand sides, then
exits after its own factors have been destroyed.  Q3 is a diagnostic interface
candidate stage; Q4/Q5 run the fresh fullspace conditional solve and Q6 writes
the cross-stage decision record.
"""

from __future__ import annotations

from contextlib import contextmanager
import gc
import hashlib
import json
import os
from pathlib import Path
import signal
import time
from types import SimpleNamespace
from typing import Any, Mapping

import numpy as np

from src.io.physical_intermediate_profile import SCHUR_PROFILE, profile_facts
from .physical_v14_budget import (
    V14_TIME_POLICY_ENFORCE,
    V14_TIME_POLICY_OBSERVE_ONLY,
    normalize_v14_time_policy,
    read_v14_effective_budget,
    v14_time_gate_facts,
    v14_time_policy_facts,
)


_Q1_Q2_RHS = (
    {
        "stem": "A2R160_BAL_H_p4_01",
        "input_json": "benchmarks/artifacts/task39extra/v5_balanced/c4e86cfe1e6ba88ca5d26df82942e82f190e7eda/e1/A2R160_BAL_H_p4_01_input.json",
        "input_sha256": "630d72b522ea2fe87d124833c031206708bbde1be1aca12e9bdf113af6c1c6a1",
        "input_npz_sha256": "a630483a3fb3b6dac145809545ac3768b8ff22dd15aad8f7e6f2fff43068b268",
        "g_sha256": "f768ff33bdd7d87844126da745897462793ac8d7f10d63eca0b7e5df65624c35",
        "reference_json": "benchmarks/artifacts/task39extra/v5_balanced/c4e86cfe1e6ba88ca5d26df82942e82f190e7eda/e1/A2R160_BAL_H_p4_01_residual_0.json",
        "reference_json_sha256": "100adfa1791943951d356ee3741f42ae8700df584491c9432bed5c5ba4c54b75",
        "reference_npz_sha256": "2eef8af221f793df08eb95ed475f409d8b84e4c3defe5a96fa7a01473441bd0f",
        "logical_rhs": 1,
    },
    {
        "stem": "A2R160_BAL_H_p4_02",
        "input_json": "benchmarks/artifacts/task39extra/v5_balanced/c4e86cfe1e6ba88ca5d26df82942e82f190e7eda/e1/A2R160_BAL_H_p4_02_input.json",
        "input_sha256": "bd67fd98422179f6a66d0cbbb7a958e738b0acdad8905e11e0182f9496d85826",
        "input_npz_sha256": "ac3d29e8dc50f1c8ff46e7e11546b6b66702270e8183026ce0393674327c5bd9",
        "g_sha256": "9f80339733111712644f976d6ed7728d4a8ea0a0c9ddc2f70079ebf2fbd12fb8",
        "reference_json": "benchmarks/artifacts/task39extra/v5_balanced/c4e86cfe1e6ba88ca5d26df82942e82f190e7eda/e1/A2R160_BAL_H_p4_02_residual_0.json",
        "reference_json_sha256": "e07c05442ffc9a0544ce50c8c054439d48770b773e6b95f4311feafb05a06c20",
        "reference_npz_sha256": "5a166d02c8c62dff444e339539525521a30dbdaa8023838fa5edf94f29a939f3",
        "logical_rhs": 2,
    },
    {
        "stem": "LIGHT448_BAL_H_p4_09",
        "input_json": "benchmarks/artifacts/task39extra/v5_balanced/c4e86cfe1e6ba88ca5d26df82942e82f190e7eda/e1/LIGHT448_BAL_H_p4_09_input.json",
        "input_sha256": "e3a919807e5d80f20e7e96b58626ea6e392a32e5b5280e0a175452b133cb2e76",
        "input_npz_sha256": "212700de37917f3f706395e08d8c645333fcfbebad236d649f14bcf415144728",
        "g_sha256": "dc121f45e8ffe2105a61b9cfc0783b600d1b6c155223dd49029a7017be27e24e",
        "reference_json": "benchmarks/artifacts/task39extra/v5_balanced/c4e86cfe1e6ba88ca5d26df82942e82f190e7eda/e1/LIGHT448_BAL_H_p4_09_residual_0.json",
        "reference_json_sha256": "3fa6f5c510db29d38276ee9aa299b527bb083be9335e66528c12d727c7acef24",
        "reference_npz_sha256": "3b28af8443fd61df198a86ad4f4adc8228bb7caaa29ba23a17f7d9af639cc3fa",
        "logical_rhs": 9,
    },
)


_V21_REFERENCE_PRE_NUMERIC_RHS_JSON_SHA256 = (
    "d816a30dca0718116d989c06d79c72b13fe9cd93d2dd6e9ea7470af0eb1d7ef7"
)
_V21_REFERENCE_PRE_NUMERIC_RHS_NPZ_SHA256 = (
    "9b24bb578baeb6ed314292f02e2812429930e71fb1ab8f388cf9efa7e90941ea"
)


class V14ResourceStop(RuntimeError):
    """A measured resource or time boundary stopped the current stage."""

    def __init__(self, message: str, *, classification="RESOURCE_CONTROLLED_STOP"):
        super().__init__(message)
        self.classification = classification


class V20ReleaseGateStop(RuntimeError):
    """A finite but unqualified pre-release V20 residual gate."""

    def __init__(self, facts: Mapping[str, Any]):
        self.facts = dict(facts)
        self.classification = "V20_RELEASE_GATE_FAIL"
        super().__init__(self.classification + ": " + json.dumps(
            _jsonable(self.facts), sort_keys=True, separators=(",", ":")
        ))


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    from .physical_diagnosis_worker import _sha256_file as chunked_sha256_file

    return chunked_sha256_file(path)


def _jsonable(value: Any) -> Any:
    """Keep JSON evidence compact while retaining array identity hashes."""

    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        array = np.ascontiguousarray(value)
        return {
            "shape": list(array.shape),
            "dtype": str(array.dtype),
            "sha256": _sha256_bytes(array.tobytes()),
        }
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, complex):
        return {"real": float(value.real), "imag": float(value.imag)}
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    encoded = (
        json.dumps(
            _jsonable(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(encoded)
    os.replace(temporary, path)


def _append_jsonl(path: Path, value: Mapping[str, Any]) -> None:
    with path.open("ab") as stream:
        stream.write(
            (
                json.dumps(
                    _jsonable(value),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )
                + "\n"
            ).encode("utf-8")
        )
        stream.flush()
        os.fsync(stream.fileno())


def _save_packet(
    directory: Path,
    name: str,
    facts: Mapping[str, Any],
    *,
    runtime: _V14Runtime | None = None,
) -> dict[str, Any]:
    """Reuse the audited packet writer for immediate vector evidence."""

    from .physical_diagnosis_worker import save_packet

    directory.mkdir(parents=True, exist_ok=True)
    workspace_label = f"packet_{name}"
    if runtime is not None:
        runtime.reserve_workspace(workspace_label, 17 << 20)
    try:
        save_packet(directory, name, dict(facts))
    finally:
        if runtime is not None:
            runtime.release_workspace(workspace_label)
    packet_path = directory / f"{name}.json"
    return json.loads(packet_path.read_text(encoding="utf-8"))


def _repo_root() -> Path:
    for candidate in (Path(__file__).resolve().parent, *Path(__file__).resolve().parents):
        if (candidate / "src").is_dir() and (candidate / "input").is_dir():
            return candidate
    raise RuntimeError("V14 worker cannot locate the repository root")


def _load_rhs_and_reference(root: Path, storage_rows: int) -> list[dict[str, Any]]:
    """Load the three reviewed packets through the audited calibration loader.

    ``load_recursive_calibration`` binds ``g``, ``y``, ``A4y`` and the frozen
    native p4 constraint map together.  The current worker still rebuilds its
    mesh and operators, then checks those identities before any factor is
    built; the old packet is never used as a solver setup shortcut.
    """

    from .physical_recursive_controls import load_recursive_calibration

    inventory_path = root / "benchmarks/artifacts/task39extra/v6_recursive/g0_inventory.json"
    loaded = load_recursive_calibration(inventory_path)
    wanted = {item["stem"]: item for item in _Q1_Q2_RHS}
    selected = {
        item["identity"]["stem"]: item
        for item in loaded
        if item["identity"].get("stem") in wanted
    }
    if tuple(selected) != tuple(item["stem"] for item in _Q1_Q2_RHS):
        raise ValueError("V14 calibration loader did not return the reviewed RHS order")
    result = []
    for item in _Q1_Q2_RHS:
        loaded_item = selected[item["stem"]]
        identity = loaded_item["identity"]
        input_json = root / item["input_json"]
        input_npz = input_json.with_suffix(".npz")
        reference_json = root / item["reference_json"]
        reference_metadata = json.loads(reference_json.read_text(encoding="utf-8"))
        reference_npz = root / reference_metadata["arrays"]["path"]
        if identity.get("input_sha256") != item["input_sha256"]:
            raise ValueError(f"{item['stem']} calibration identity changed")
        for path, expected, label in (
            (input_json, item["input_sha256"], "input metadata"),
            (input_npz, item["input_npz_sha256"], "input array"),
            (reference_json, item["reference_json_sha256"], "reference metadata"),
            (reference_npz, item["reference_npz_sha256"], "reference array"),
        ):
            if _sha256_file(path) != expected:
                raise ValueError(f"{item['stem']} {label} hash changed")
        rhs = np.ascontiguousarray(loaded_item["rhs"], dtype=np.complex128).copy()
        reference = np.ascontiguousarray(
            loaded_item["reference_y"], dtype=np.complex128
        ).copy()
        reference_A4y = np.ascontiguousarray(
            loaded_item["reference_A4y"], dtype=np.complex128
        ).copy()
        if rhs.shape != (storage_rows,) or reference.shape != (storage_rows,):
            raise ValueError(f"{item['stem']} p4 storage vector shape changed")
        if reference_A4y.shape != (storage_rows,):
            raise ValueError(f"{item['stem']} saved A4y shape changed")
        if _sha256_bytes(rhs.tobytes()) != item["g_sha256"]:
            raise ValueError(f"{item['stem']} RHS content hash changed")
        result.append(
            {
                "stem": item["stem"],
                "logical_rhs": int(item["logical_rhs"]),
                "rhs": rhs,
                "reference_solution": reference,
                "reference_A4y": reference_A4y,
                "reference_identity": loaded_item.get("reference_identity"),
                "reference_map": loaded_item["reference_map"],
                "calibration_identity": identity,
                "input_json": str(input_json),
                "input_npz": str(input_npz),
                "input_sha256": item["input_sha256"],
                "input_npz_sha256": item["input_npz_sha256"],
                "g_sha256": item["g_sha256"],
                "reference_json": str(reference_json),
                "reference_json_sha256": item["reference_json_sha256"],
                "reference_npz": str(reference_npz),
                "reference_npz_sha256": item["reference_npz_sha256"],
                "reference_true_residual": reference_metadata.get("final_true_residual"),
            }
        )
    # Make the fact that only the three reviewed entries remain explicit.
    for item in loaded:
        if item["identity"].get("stem") not in wanted:
            del item["rhs"]
            if item.get("reference_y") is not None:
                del item["reference_y"]
            if item.get("reference_A4y") is not None:
                del item["reference_A4y"]
    return result


class _V14Runtime:
    """Worker ledger with separate resident-RSS and live-inventory gates."""

    SHARED_WORKFLOW_SECONDS = 43_200.0

    def __init__(
        self,
        directory: Path,
        stage: str,
        contract: Mapping[str, Any],
        *,
        root: Path,
        source_sha: str,
        batch_identity: str = "review_v14",
        evidence_prefix: str = "v14",
        require_zero_swap: bool = True,
    ) -> None:
        self.directory = directory
        self.stage = stage
        self.contract = contract
        self.root = root
        self.source_sha = source_sha
        self.batch_identity = str(batch_identity)
        self.evidence_prefix = str(evidence_prefix)
        self.require_zero_swap = bool(require_zero_swap)
        if not self.batch_identity or not self.evidence_prefix:
            raise ValueError("runtime batch identity and evidence prefix are required")
        self.events_path = directory / f"{self.evidence_prefix}_events.jsonl"
        self.resources_path = directory / f"{self.evidence_prefix}_worker_resources.jsonl"
        self.inventory_path = directory / f"{self.evidence_prefix}_inventory.json"
        self.phase_path = Path(
            os.environ.get("PHYSICAL_WATCHDOG_PHASE_PATH", directory / "workflow_phase.json")
        )
        self.parent_pid = int(os.environ.get("PHYSICAL_WATCHDOG_PARENT_PID", "-1"))
        resources = contract["resources"]
        from benchmarks.subreaper_watchdog import (
            LEGACY_MEMORY_POLICY,
            PHYSICAL_MEMORY_PRESSURE_POLICY,
        )

        self.memory_policy = str(
            resources.get("watchdog_memory_policy", LEGACY_MEMORY_POLICY)
        )
        worker_policy = os.environ.get(
            "PHYSICAL_WATCHDOG_MEMORY_POLICY", self.memory_policy
        )
        if worker_policy != self.memory_policy:
            raise RuntimeError(
                "worker/watchdog memory policy differs from resolved contract"
            )
        self.physical_memory_pressure = (
            self.memory_policy == PHYSICAL_MEMORY_PRESSURE_POLICY
        )
        if self.physical_memory_pressure:
            self.parent_cap = None
            self.inventory_cap = None
            self.workspace_cap = None
        else:
            self.parent_cap = int(
                os.environ.get(
                    "PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES",
                    resources["tree_cap_bytes"],
                )
            )
            self.inventory_cap = resources[
                "inventory_memory_cap_bytes_by_stage"
            ].get(stage)
            self.workspace_cap = int(resources["shared_temp_workspace_cap_bytes"])
        self.stop_requested = False
        self.pc_soft_stop_requested = False
        self._pc_clock = None
        self._outer_solve_active = False
        self._phase_record = None
        self._phase = "preflight"
        self.inventory_entries: dict[str, dict[str, Any]] = {}
        self.inventory_used_bytes = 0
        self.inventory_peak_bytes = 0
        self.workspace_entries: dict[str, int] = {}
        self.workspace_live_bytes = 0
        self.workspace_peak_bytes = 0
        parent_ledger = os.environ.get("PHYSICAL_WATCHDOG_SHARED_LEDGER_PATH")
        if parent_ledger is None:
            raise RuntimeError(
                "V14 worker requires the parent-owned shared workflow ledger"
            )
        self._ledger_path = Path(parent_ledger)
        self._stage_attempt_index = int(
            os.environ.get("PHYSICAL_WATCHDOG_SHARED_ATTEMPT_INDEX", "-1")
        )
        if self._stage_attempt_index < 0:
            raise RuntimeError("V14 parent ledger attempt index is missing")
        shared_ledger = json.loads(self._ledger_path.read_text(encoding="utf-8"))
        if shared_ledger.get("batch_identity") != self.batch_identity:
            raise RuntimeError("parent ledger batch identity changed")
        attempts = list(
            shared_ledger.get("stages", {}).get(self.stage, {}).get("attempts", [])
        )
        if not 0 <= self._stage_attempt_index < len(attempts):
            raise RuntimeError("V14 parent ledger attempt is missing")
        attempt = attempts[self._stage_attempt_index]
        if attempt.get("source_sha") != self.source_sha:
            raise RuntimeError("V14 parent ledger source SHA differs from worker")
        if attempt.get("status") not in {"RESERVED", "RUNNING"}:
            raise RuntimeError("V14 parent ledger attempt is not live")
        try:
            self.shared_budget = read_v14_effective_budget(shared_ledger)
        except ValueError as exc:
            raise RuntimeError(f"V14 shared ledger budget is invalid: {exc}") from exc
        self.shared_attempt = dict(attempt)
        try:
            self.time_policy = normalize_v14_time_policy(
                attempt.get("time_policy")
            )
        except ValueError as exc:
            raise RuntimeError(f"V14 parent time policy is invalid: {exc}") from exc
        self.time_policy_facts = v14_time_policy_facts(self.time_policy)
        self.infrastructure_recovery = (
            attempt.get("recovery_id") == "V15_Q0_EIO_ONCE"
        )
        workflow_clock_start = attempt.get("workflow_clock_start")
        reserved_seconds = attempt.get("reserved_seconds")
        workflow_clock_source = "parent_attempt.workflow_clock_start"
        if not isinstance(workflow_clock_start, Mapping):
            raise RuntimeError("V14 parent workflow clock start is missing")
        if (
            not isinstance(reserved_seconds, (int, float))
            or not np.isfinite(float(reserved_seconds))
            or float(reserved_seconds) <= 0.0
        ):
            raise RuntimeError("V14 parent workflow reservation is invalid")
        self.workflow_clock_start = dict(workflow_clock_start)
        self.workflow_reserved_seconds = float(reserved_seconds)
        self.workflow_clock_source = workflow_clock_source
        from .workflow_timebase import ClockBudget, CONSERVATIVE_REALTIME

        self._workflow_clock = ClockBudget(
            self.workflow_clock_start, policy=CONSERVATIVE_REALTIME
        )
        self.phase_path.parent.mkdir(parents=True, exist_ok=True)
        self.set_phase(self._phase)
        self._persist_inventory()

    def _persist_inventory(self) -> None:
        component_totals: dict[str, int] = {}
        for entry in self.inventory_entries.values():
            for key, value in entry["components"].items():
                component_totals[key] = component_totals.get(key, 0) + int(value)
            component_totals["workspace_bytes"] = component_totals.get(
                "workspace_bytes", 0
            ) + int(entry.get("workspace_bytes", 0))
        _write_json(
            self.inventory_path,
            {
                "schema": f"task039extra.{self.evidence_prefix}.inventory-ledger.v1",
                "stage": self.stage,
                "source_sha": self.source_sha,
                "inventory_cap_bytes": self.inventory_cap,
                "inventory_used_bytes": self.inventory_used_bytes,
                "inventory_peak_bytes": self.inventory_peak_bytes,
                "workspace_cap_bytes": self.workspace_cap,
                "workspace_live_bytes": self.workspace_live_bytes,
                "workspace_peak_bytes": self.workspace_peak_bytes,
                "component_totals": component_totals,
                "entries": self.inventory_entries,
            },
        )

    def workflow_clock_interval(self) -> dict[str, Any]:
        """Return elapsed time from the parent attempt's immutable clock start."""

        from .workflow_timebase import clock_sample

        return self._workflow_clock.update(clock_sample())

    def _inventory_size(self, components: Mapping[str, int]) -> int:
        values = {str(key): int(value) for key, value in components.items()}
        if any(value < 0 for value in values.values()):
            raise ValueError("V14 inventory components cannot be negative")
        return int(sum(values.values()))

    def reserve_inventory(
        self,
        label: str,
        components: Mapping[str, int],
        *,
        workspace_bytes: int = 0,
        check_rss: bool = True,
    ) -> dict[str, Any]:
        key = str(label)
        if workspace_bytes:
            raise ValueError("reserve workspace separately with reserve_workspace")
        if key in self.inventory_entries:
            raise RuntimeError(f"V14 inventory label is already live: {key}")
        normalized = {str(name): int(value) for name, value in components.items()}
        amount = self._inventory_size(normalized)
        if check_rss:
            self.check_projected(key, amount)
        self.check_inventory_projected(key, amount)
        projected = self.inventory_used_bytes + amount
        if self.inventory_cap is not None and projected > int(self.inventory_cap):
            raise V14ResourceStop(
                f"V14 live inventory exceeds stage cap: {key} {projected}>{self.inventory_cap}"
            )
        entry = {
            "components": normalized,
            "bytes": amount,
            "reserved_timestamp_ns": time.time_ns(),
        }
        self.inventory_entries[key] = entry
        self.inventory_used_bytes = projected
        self.inventory_peak_bytes = max(self.inventory_peak_bytes, projected)
        self._persist_inventory()
        self.marker(
            "v14_inventory_reserved",
            {"label": key, "entry": entry, "used_bytes": projected},
        )
        return entry

    def check_inventory_projected(self, label: str, amount: int) -> dict[str, Any]:
        projected = self.inventory_used_bytes + int(amount)
        facts = {
            "label": str(label),
            "current_inventory_bytes": self.inventory_used_bytes,
            "projected_inventory_bytes": projected,
            "inventory_cap_bytes": self.inventory_cap,
            "gate": "independent_live_inventory_cap",
        }
        self.marker("v14_projected_inventory_gate", facts)
        if self.inventory_cap is not None and projected > int(self.inventory_cap):
            raise V14ResourceStop(f"V14 projected live inventory exceeds cap: {facts}")
        return facts

    def replace_inventory(self, label: str, components: Mapping[str, int]) -> None:
        key = str(label)
        old = self.inventory_entries.get(key)
        if old is None:
            raise RuntimeError(f"V14 inventory label is not live: {key}")
        normalized = {str(name): int(value) for name, value in components.items()}
        amount = self._inventory_size(normalized)
        projected = self.inventory_used_bytes - int(old["bytes"]) + amount
        if self.inventory_cap is not None and projected > int(self.inventory_cap):
            raise V14ResourceStop(
                f"V14 replaced inventory exceeds stage cap: {key} {projected}>{self.inventory_cap}"
            )
        self.inventory_entries[key] = {
            "components": normalized,
            "bytes": amount,
            "replaced_timestamp_ns": time.time_ns(),
            "reserved_upper_bound_bytes": int(old["bytes"]),
        }
        self.inventory_used_bytes = projected
        self.inventory_peak_bytes = max(self.inventory_peak_bytes, projected)
        self._persist_inventory()
        self.marker(
            "v14_inventory_replaced",
            {"label": key, "old_bytes": old["bytes"], "new_bytes": amount},
        )

    def reserve_workspace(self, label: str, workspace_bytes: int) -> None:
        key = str(label)
        amount = int(workspace_bytes)
        if amount < 0:
            raise ValueError("V14 workspace allocation cannot be negative")
        if key in self.workspace_entries:
            raise RuntimeError(f"V14 workspace label is already live: {key}")
        self.check_workspace_projected(key, amount)
        self.check_projected(key, 0, workspace_bytes=amount)
        projected = self.workspace_live_bytes + amount
        if self.workspace_cap is not None and projected > self.workspace_cap:
            raise V14ResourceStop(
                f"V14 shared temporary workspace exceeds cap: {key} {projected}>{self.workspace_cap}"
            )
        self.workspace_entries[key] = amount
        self.workspace_live_bytes = projected
        self.workspace_peak_bytes = max(self.workspace_peak_bytes, projected)
        self._persist_inventory()
        self.marker(
            "v14_workspace_reserved",
            {"label": key, "bytes": amount, "live_bytes": projected},
        )

    def check_workspace_projected(self, label: str, workspace_bytes: int) -> dict[str, Any]:
        amount = int(workspace_bytes)
        if amount < 0:
            raise ValueError("V14 workspace allocation cannot be negative")
        projected = self.workspace_live_bytes + amount
        facts = {
            "label": str(label),
            "current_workspace_bytes": self.workspace_live_bytes,
            "projected_workspace_bytes": projected,
            "workspace_cap_bytes": self.workspace_cap,
            "gate": "independent_shared_temporary_workspace_cap",
        }
        self.marker("v14_projected_workspace_gate", facts)
        if self.workspace_cap is not None and projected > self.workspace_cap:
            raise V14ResourceStop(f"V14 projected workspace exceeds cap: {facts}")
        return facts

    def release_workspace(self, label: str) -> None:
        key = str(label)
        amount = self.workspace_entries.pop(key, None)
        if amount is None:
            return
        self.workspace_live_bytes -= amount
        if self.workspace_live_bytes < 0:
            raise RuntimeError("V14 workspace ledger became negative")
        self._persist_inventory()
        self.marker(
            "v14_workspace_released",
            {"label": key, "bytes": amount, "live_bytes": self.workspace_live_bytes},
        )

    def release_inventory(self, label: str) -> None:
        key = str(label)
        entry = self.inventory_entries.pop(key, None)
        if entry is None:
            return
        self.inventory_used_bytes -= int(entry["bytes"])
        if self.inventory_used_bytes < 0:
            raise RuntimeError("V14 inventory ledger became negative")
        self._persist_inventory()
        self.marker(
            "v14_inventory_released",
            {"label": key, "bytes": entry["bytes"], "used_bytes": self.inventory_used_bytes},
        )

    def check_projected(
        self,
        label: str,
        allocation_bytes: int,
        *,
        workspace_bytes: int = 0,
    ) -> dict[str, Any]:
        resource = self.sample(f"{label}_projected")
        allocation = int(allocation_bytes)
        workspace = int(workspace_bytes)
        if allocation < 0 or workspace < 0:
            raise ValueError("V14 projected allocation cannot be negative")
        workspace_live = int(self.workspace_live_bytes)
        untouched_workspace = (
            max(0, self.workspace_cap - workspace_live - workspace)
            if self.workspace_cap is not None
            else 0
        )
        # The current RSS sample already contains any workspace that has
        # materialized.  The still-unmaterialized part of the single shared
        # workspace pool is carried as a conservative future-copy reserve;
        # the new workspace request and that remainder together never exceed
        # the same 1 GiB pool.
        projected_rss = (
            int(resource["rss_bytes"])
            + allocation
            + workspace
            + untouched_workspace
        )
        facts = {
            "label": str(label),
            "allocation_bytes": allocation,
            "workspace_bytes": workspace,
            "workspace_live_bytes": workspace_live,
            "workspace_untouched_reserve_bytes": untouched_workspace,
            "workspace_pool_cap_bytes": self.workspace_cap,
            "rss_bytes": int(resource["rss_bytes"]),
            "projected_rss_bytes": projected_rss,
            "launch_cap_bytes": int(resource["launch_cap_bytes"]),
            "gate": (
                "live_physical_pressure_sample_only"
                if self.physical_memory_pressure
                else "rss_includes_live_workspace_plus_new_workspace_plus_"
                "untouched_shared_workspace_reserve"
            ),
            "survival_assumption": (
                "all currently reserved workspace is resident in sampled RSS; "
                "the unmaterialized remainder may appear with the next allocation"
            ),
        }
        self.marker("v14_projected_allocation_gate", facts)
        if (
            not self.physical_memory_pressure
            and projected_rss >= int(resource["launch_cap_bytes"])
        ):
            raise V14ResourceStop(f"V14 projected resident allocation exceeds cap: {facts}")
        return facts

    def set_phase(self, phase: str) -> None:
        if self._outer_solve_active and phase != "solve":
            self._phase_record["solve_subphase"] = str(phase)
            _write_json(self.phase_path, self._phase_record)
            return
        if self._phase_record is not None and phase == self._phase:
            return
        self._phase = str(phase)
        from .workflow_timebase import clock_sample

        clock = clock_sample() if os.environ.get("PHYSICAL_TIMEBASE_GUARD") == "1" else None
        value = {
            "schema": "task039extra.v14.workflow-phase.v1",
            "phase": self._phase,
            "stage": self.stage,
            "phase_started_monotonic": time.monotonic(),
            "phase_started_clock": clock,
            "clock_error": None,
            "active_pc": None,
        }
        self._phase_record = value
        _write_json(self.phase_path, value)

    def begin_outer_solve(self) -> None:
        """Anchor the single KSP run, including all in-solve checkpoints."""

        if self._outer_solve_active or self._pc_clock is not None:
            raise RuntimeError("cannot restart an active V14 outer solve")
        # Earlier setup/backsolve probes may also have used the solve phase.
        # Only this explicit transition establishes the one outer KSP start.
        self._phase_record = None
        self.set_phase("solve")
        self._outer_solve_active = True

    def finish_outer_solve(self) -> None:
        if not self._outer_solve_active or self._pc_clock is not None:
            raise RuntimeError("V14 outer solve must finish between whole PC actions")
        self._outer_solve_active = False

    def begin_pc(self, sequence: int) -> None:
        """Arm the parent deadline for one whole BAL_H action."""

        from .workflow_timebase import ClockBudget, CONSERVATIVE_REALTIME, clock_sample

        if self._pc_clock is not None:
            raise RuntimeError("a whole V14 PC action is already active")
        self.set_phase("solve")
        start = clock_sample()
        self._pc_clock = ClockBudget(start, policy=CONSERVATIVE_REALTIME)
        self._phase_record["active_pc"] = {
            "sequence": int(sequence), "started_clock": start,
        }
        self._phase_record["solve_subphase"] = "pc"
        _write_json(self.phase_path, self._phase_record)

    def finish_pc(self, *, completed: bool = True) -> dict[str, Any]:
        """Disarm after return and request soft stop only for a complete PC."""

        from .workflow_timebase import clock_sample

        if self._pc_clock is None:
            raise RuntimeError("no whole V14 PC action is active")
        interval = self._pc_clock.update(clock_sample())
        active_pc = dict(self._phase_record["active_pc"])
        # The numerical action has returned even if its observation metadata
        # is invalid. Disarm before validating it so cleanup preserves that
        # original error instead of reporting a still-active PC.
        self._phase_record["active_pc"] = None
        self._phase_record["solve_subphase"] = "between_pc"
        self._pc_clock = None
        _write_json(self.phase_path, self._phase_record)
        soft_limit = float(self.contract["resources"]["pc_soft_seconds"])
        hard_limit = float(self.contract["resources"]["pc_hard_seconds"])
        soft_time = v14_time_gate_facts(
            interval["budget_seconds"], soft_limit, self.time_policy, inclusive=True
        )
        hard_time = v14_time_gate_facts(
            interval["budget_seconds"], hard_limit, self.time_policy, inclusive=True
        )
        facts = {
            **active_pc,
            "completed": bool(completed),
            "clock_interval": interval,
            "soft_limit_seconds": soft_limit,
            "hard_limit_seconds": hard_limit,
            **self.time_policy_facts,
            "soft_time_gate": soft_time,
            "hard_time_gate": hard_time,
        }
        if (
            completed
            and self.time_policy == V14_TIME_POLICY_ENFORCE
            and interval["budget_seconds"] >= facts["soft_limit_seconds"]
        ):
            self.pc_soft_stop_requested = True
        facts["soft_stop_requested"] = self.pc_soft_stop_requested
        facts["hard_limit_exceeded"] = (
            interval["budget_seconds"] >= facts["hard_limit_seconds"]
        )
        self.marker("v14_whole_pc_returned", facts)
        if (
            completed
            and facts["hard_limit_exceeded"]
            and self.time_policy == V14_TIME_POLICY_ENFORCE
        ):
            raise V14ResourceStop(
                f"PC_TIME_CONTROLLED_STOP: {facts}",
                classification="PC_TIME_CONTROLLED_STOP",
            )
        return facts

    def marker(self, name: str, facts: Mapping[str, Any] | None = None) -> None:
        if self._pc_clock is None and name.endswith("started"):
            if "numeric" in name or "symbolic" in name or "factor" in name:
                self.set_phase("factor")
            elif "solve" in name:
                self.set_phase("solve")
            elif "assembly" in name or "compile" in name:
                self.set_phase("assembly")
        _append_jsonl(
            self.events_path,
            {
                "event": name,
                "stage": self.stage,
                "timestamp_ns": time.time_ns(),
                "facts": {} if facts is None else facts,
            },
        )

    def sample(
        self, label: str | None = None, *, enforce: bool = True
    ) -> dict[str, Any]:
        """Record one live resource sample, optionally without raising a gate.

        The V22 numeric observer uses ``enforce=False`` only after it has
        durably saved native factor facts.  All historical callers retain the
        enforcing default.
        """

        if enforce and self.stop_requested:
            raise V14ResourceStop("parent requested a V14 worker stop")
        if self._pc_clock is not None:
            from .workflow_timebase import clock_sample

            self._pc_clock.update(clock_sample())
        if self.parent_pid <= 0 or self.parent_pid == os.getpid() or not Path(
            f"/proc/{self.parent_pid}"
        ).is_dir():
            raise RuntimeError("V14 worker requires the dedicated parent watchdog")
        from benchmarks.subreaper_watchdog import memory_envelope
        from benchmarks.task038_full3d_jit_staging import process_tree_snapshot

        value = process_tree_snapshot(self.parent_pid, self._phase, None)
        envelope = memory_envelope(self.memory_policy)
        dynamic_cap = (
            int(value["rss_bytes"])
            + int(envelope["effective_available_bytes"])
            - int(envelope["reserve_bytes"])
        )
        cap = dynamic_cap if self.physical_memory_pressure else min(self.parent_cap, dynamic_cap)
        value.update(
            {
                "label": label,
                "memory_envelope": envelope,
                "launch_cap_bytes": cap,
                "parent_tree_cap_bytes": self.parent_cap,
                "inventory_memory_cap_bytes": self.inventory_cap,
                "inventory_used_bytes": self.inventory_used_bytes,
                "inventory_peak_bytes": self.inventory_peak_bytes,
                "workspace_live_bytes": self.workspace_live_bytes,
                "workspace_peak_bytes": self.workspace_peak_bytes,
                "require_zero_swap": self.require_zero_swap,
                "swap_policy": (
                    "require_zero_swap" if self.require_zero_swap else "observe_only"
                ),
                "cap_policy": (
                    "current_tree_rss+available-reserve; no startup/static cap"
                    if self.physical_memory_pressure
                    else "min(parent_tree_cap,current_tree_rss+available-reserve)"
                ),
                "inventory_policy": (
                    "record_only_under_physical_memory_pressure"
                    if self.physical_memory_pressure
                    else "independent_live_matrix_factor_coupling_workspace_sum"
                ),
                **self.time_policy_facts,
            }
        )
        _append_jsonl(self.resources_path, value)
        if enforce and (
            not value["all_status_readable"]
            or (self.require_zero_swap and int(value["swap_bytes"]) != 0)
            or int(envelope["effective_available_bytes"]) < int(envelope["reserve_bytes"])
            or int(value["rss_bytes"]) >= cap
            or (
                self.inventory_cap is not None
                and self.inventory_used_bytes > int(self.inventory_cap)
            )
            or (
                self.workspace_cap is not None
                and self.workspace_live_bytes > self.workspace_cap
            )
        ):
            raise V14ResourceStop(f"V14 {self.stage} resource gate failed: {value}")
        return value

def _abi_facts() -> dict[str, Any]:
    from .fine_reference_preflight import qualified_abi

    return qualified_abi()


def _v14_known_preallocation_gate(
    runtime: _V14Runtime,
    stage: str,
    *,
    include_common: bool = True,
    include_matrices: bool = True,
) -> None:
    """Gate known allocations at the point where their live peers exist.

    The common-cache estimate is checked before constructing the common core.
    The Q1/Q2 sparse-object estimate is checked later, after the common core
    and reviewed RHS packets are live and immediately before volume creation.
    Thus the second check uses the sampled RSS containing the actual common
    objects rather than an empty-process estimate.
    """

    p6_storage_rows = 173802
    p4_storage_rows = 53084
    p4_volume_nnz = 24730144
    p4_augmented_rows = 53164
    p4_augmented_nnz = 24730144
    port_count = 80
    index_bytes = 4
    scalar_bytes = 16

    # This is an auditable count-based estimate for retained common payloads:
    # four volume component actions, two metric actions, two known 6-to-4
    # transfer plan/cache families, and the two 80-port carriers.  The
    # allowance terms are derived conservative estimates from the review
    # inventory assumptions; they are not mathematical strict upper bounds.
    component_vectors = 4 * (p6_storage_rows + p4_storage_rows) * scalar_bytes * 8
    component_indices = 4 * (p6_storage_rows + p4_storage_rows) * index_bytes * 8
    metric_vectors = 2 * p6_storage_rows * scalar_bytes * 8
    transfer_and_owner_plan = 256 * 1024**2
    carrier_and_mode_metadata = 64 * 1024**2 + port_count * scalar_bytes * 8
    common_upper = (
        component_vectors
        + component_indices
        + metric_vectors
        + transfer_and_owner_plan
        + carrier_and_mode_metadata
    )
    common_facts = {
        "stage": stage,
        "allocation_bytes": int(common_upper),
        "estimate_classification": "derived_conservative_estimate",
        "strict_upper_bound": False,
        "formula": {
            "component_vectors": "4*(N6_storage+N4_storage)*16*8",
            "component_indices": "4*(N6_storage+N4_storage)*4*8",
            "metric_vectors": "2*N6_storage*16*8",
            "transfer_and_owner_plan": (
                "implementation-derived 256MiB estimate from current owner-routing "
                "arrays and plan storage; not separately calibrated"
            ),
            "carrier_and_mode_metadata": (
                "implementation-derived 64MiB estimate for current carrier/mode "
                "metadata plus 80*16*8; not separately calibrated"
            ),
        },
        "assumptions": [
            "common component arrays and index maps remain resident through Q1/Q2",
            "the 256MiB and 64MiB terms cover implementation-dependent metadata",
            "these implementation estimates are conservative but not strict allocation proofs",
        ],
        "counts": {
            "p6_storage_rows": p6_storage_rows,
            "p4_storage_rows": p4_storage_rows,
            "port_count": port_count,
        },
        "gate": "known_common_payload_before_build",
    }
    if include_common:
        runtime.check_projected("common_setup_preallocation", common_upper)
        runtime.marker("v14_common_preallocation_gate", common_facts)

    if not include_matrices:
        return

    volume_payload = (p4_storage_rows + 1) * index_bytes + p4_volume_nnz * (
        index_bytes + scalar_bytes
    )
    augmented_payload = (p4_augmented_rows + 1) * index_bytes + p4_augmented_nnz * (
        index_bytes + scalar_bytes
    )
    if stage in {
        "Q1_FULL_DIRECT",
        "S2_BLR_CONTROL",
        "T1_BLR_CONTROL",
        "T2_BLR_CONTROL",
    }:
        pair_upper = volume_payload + augmented_payload + 128 * 1024**2
        gate_label = {
            "Q1_FULL_DIRECT": "q1_original_volume_and_augmented_preallocation",
            "S2_BLR_CONTROL": "s2_blr_volume_and_augmented_preallocation",
            "T1_BLR_CONTROL": "t1_blr_volume_and_augmented_preallocation",
            "T2_BLR_CONTROL": "t2_blr_volume_and_augmented_preallocation",
        }[stage]
        marker_name = {
            "Q1_FULL_DIRECT": "q1_original_sparse_preallocation_gate",
            "S2_BLR_CONTROL": "v16_s2_blr_sparse_preallocation_gate",
            "T1_BLR_CONTROL": "v17_t1_blr_sparse_preallocation_gate",
            "T2_BLR_CONTROL": "v17_t2_blr_sparse_preallocation_gate",
        }[stage]
        runtime.check_projected(
            gate_label, pair_upper
        )
        runtime.marker(
            marker_name,
            {
                "volume_rows": p4_storage_rows,
                "volume_nnz_upper": p4_volume_nnz,
                "volume_payload_bytes": volume_payload,
                "augmented_rows": p4_augmented_rows,
                "augmented_nnz_upper": p4_augmented_nnz,
                "augmented_payload_bytes": augmented_payload,
                "temporary_workspace_upper_bytes": 128 * 1024**2,
                "simultaneous_upper_bytes": pair_upper,
                "estimate_classification": "derived_conservative_estimate",
                "strict_upper_bound": False,
                "allowance_basis": (
                    "implementation-derived 128MiB temporary assembly estimate from "
                    "sparse-construction and packet-copy assumptions; not separately calibrated"
                ),
                "gate": "volume_and_augmented_sparse_objects_live_together",
            },
        )
    elif stage == "Q2_SCHUR_DIRECT":
        runtime.check_projected(
            "q2_full_and_active_volume_preallocation",
            volume_payload * 2 + 64 * 1024**2,
        )
        runtime.marker(
            "q2_volume_preallocation_gate",
            {
                "full_volume_payload_upper_bytes": volume_payload,
                "active_volume_payload_upper_bytes": volume_payload,
                "temporary_workspace_upper_bytes": 64 * 1024**2,
                "simultaneous_upper_bytes": volume_payload * 2 + 64 * 1024**2,
                "estimate_classification": "derived_conservative_estimate",
                "strict_upper_bound": False,
                "allowance_basis": (
                    "implementation-derived 64MiB temporary submatrix estimate from "
                    "active-volume construction assumptions; not separately calibrated"
                ),
                "gate": "full_and_active_sparse_objects_overlap_during_submatrix",
            },
        )
    elif stage == "Q3_INTERFACE_CONTROL":
        runtime.check_projected(
            "q3_full_and_active_volume_preallocation",
            volume_payload * 2 + 128 * 1024**2,
        )
        runtime.marker(
            "q3_volume_preallocation_gate",
            {
                "full_storage_payload_upper_bytes": volume_payload,
                "active_payload_upper_bytes": volume_payload,
                "temporary_workspace_upper_bytes": 128 * 1024**2,
                "simultaneous_upper_bytes": volume_payload * 2 + 128 * 1024**2,
                "estimate_classification": "derived_conservative_estimate",
                "strict_upper_bound": False,
                "allowance_basis": (
                    "implementation-derived active-volume and Schur construction "
                    "allowance; not a measured sparse payload"
                ),
                "gate": "q3_full_and_active_sparse_objects_before_matrix_free_release",
            },
        )
    elif stage in {"Q4_ORIGINAL", "Q5_NOTCH"}:
        runtime.check_projected(
            f"{str(stage).lower()}_full_and_active_volume_preallocation",
            volume_payload * 2 + 128 * 1024**2,
        )
        runtime.marker(
            f"{str(stage).lower()}_volume_preallocation_gate",
            {
                "full_storage_payload_upper_bytes": volume_payload,
                "active_payload_upper_bytes": volume_payload,
                "temporary_workspace_upper_bytes": 128 * 1024**2,
                "simultaneous_upper_bytes": volume_payload * 2 + 128 * 1024**2,
                "estimate_classification": "derived_conservative_estimate",
                "strict_upper_bound": False,
                "allowance_basis": (
                    "implementation-derived active-volume and Schur construction "
                    "allowance; not a measured sparse payload"
                ),
                "gate": "fresh_full_and_active_sparse_objects_before_matrix_free_release",
            },
        )
    elif stage == "Q0_CORE":
        volume_upper = volume_payload + 64 * 1024**2
        runtime.check_projected("q0_p4_volume_preallocation", volume_upper)
        runtime.marker(
            "q0_volume_preallocation_gate",
            {
                "volume_rows": p4_storage_rows,
                "volume_nnz_upper": p4_volume_nnz,
                "volume_payload_upper_bytes": volume_payload,
                "temporary_workspace_upper_bytes": 64 * 1024**2,
                "simultaneous_upper_bytes": volume_upper,
                "estimate_classification": "derived_conservative_estimate",
                "strict_upper_bound": False,
                "allowance_basis": (
                    "implementation-derived 64MiB temporary volume-assembly estimate; "
                    "not separately calibrated"
                ),
                "gate": "single_p4_volume_before_q0_partition_and_core",
            },
        )


def _build_common(
    runtime: _V14Runtime,
    cfg: Any,
    *,
    prebuilt_levels: dict[str, Any] | None = None,
    coarse_degree: int = 4,
    optimized_owner_apply: bool = False,
    fixed_serial_owner_route: bool = False,
    native_aq_projection_check: bool = False,
) -> dict[str, Any]:
    from mpi4py import MPI
    from petsc4py import PETSc
    from src.solvers.fullspace_physical_intermediate_runtime import (
        AlgebraicOwnerTransfer,
        fine_volume_quadrature_metadata,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        build_same_mesh_physical_action,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg import (
        build_same_mesh_hcurl_transfer,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_runtime import (
        build_same_mesh_hcurl_owner_transfer,
    )
    from src.solvers.physical_error_metric import LosslessFEMetric

    coarse_degree = int(coarse_degree)
    if coarse_degree not in (2, 3, 4):
        raise ValueError("physical coarse degree must be one of 2, 3, or 4")
    declared_degrees = (6, coarse_degree)
    runtime.set_phase("setup")
    runtime.marker(
        "v14_common_setup_started",
        {"levels": list(declared_degrees), "coarse_degree": coarse_degree},
    )
    levels = (
        _build_same_mesh_levels(
            cfg,
            MPI.COMM_WORLD,
            declared_degrees,
            include_positive_coefficients=True,
        )
        if prebuilt_levels is None
        else prebuilt_levels
    )
    required_levels = set(declared_degrees)
    if not required_levels.issubset(levels["spaces"]):
        raise ValueError(
            "prebuilt same-mesh levels do not contain the requested "
            f"degrees {sorted(required_levels)}"
        )
    levels["declared_degrees"] = declared_degrees
    levels["coarse_degree"] = coarse_degree
    runtime.sample("same_mesh_levels")
    quadrature, integral_records = fine_volume_quadrature_metadata(levels, cfg)
    runtime.marker(
        "v14_fine_quadrature_complete",
        {"quadrature": quadrature, "integrals": integral_records},
    )
    fine = build_same_mesh_physical_action(
        levels, cfg, 6, volume_quadrature_metadata=quadrature
    )
    runtime.sample("fine_physical_action")
    mode_inventory = (fine["modes"], fine["mode_rows"], fine["mode_sha256"])
    coarse = build_same_mesh_physical_action(
        levels,
        cfg,
        coarse_degree,
        mode_inventory=mode_inventory,
        volume_quadrature_metadata=quadrature,
    )
    runtime.sample(f"p{coarse_degree}_physical_action")
    local_transfer = build_same_mesh_hcurl_transfer(6, coarse_degree)
    transfer = build_same_mesh_hcurl_owner_transfer(
        levels["spaces"][6],
        levels["floquets"][6],
        levels["spaces"][coarse_degree],
        levels["floquets"][coarse_degree],
        local_transfer=local_transfer,
        optimized_owner_apply=optimized_owner_apply,
        fixed_serial_owner_route=fixed_serial_owner_route,
    )
    runtime.marker(
        f"v14_p6{coarse_degree}_transfer_complete",
        {"coarse_degree": coarse_degree, "transfer": transfer.audit},
    )
    metric = LosslessFEMetric(
        levels,
        6,
        cfg.k0,
        quadrature,
        build_cell_basis=False,
    )
    runtime.marker("v14_degree6_metric_complete", dict(metric=metric.audit))
    aq_projection_check = None
    warm_coarse = _new_storage_vector(levels["spaces"][coarse_degree])
    warm_p6 = None
    native_volume = projected_volume = None
    native_dtn = projected_dtn = None
    fine_volume = fine_dtn = None
    algebraic_transfer = None
    try:
        if native_aq_projection_check:
            # The production action contracts accept a strict slave-zero
            # storage vector and perform the MPC expansion internally.  Keep
            # this probe in that same contract: deterministic owned values,
            # with only the actual owned q slave rows zeroed.
            indices = np.arange(warm_coarse.array.size, dtype=np.float64)
            warm_coarse.array[:] = (
                np.sin(0.071 * (indices + 1.0))
                + 1j * 0.37 * np.cos(0.113 * (indices + 1.0))
            )
            coarse_floquet = levels["floquets"][coarse_degree]
            owned_size = int(
                coarse_floquet.mpc.function_space.dofmap.index_map.size_local
            )
            coarse_slaves = np.asarray(coarse_floquet.mpc.slaves, dtype=np.int64)
            owned_slaves = coarse_slaves[coarse_slaves < owned_size]
            warm_coarse.array[owned_slaves] = 0.0
            warm_coarse.ghostUpdate(
                addv=PETSc.InsertMode.INSERT_VALUES,
                mode=PETSc.ScatterMode.FORWARD,
            )
            probe_input = np.asarray(warm_coarse.array, dtype=np.complex128).copy()
            probe_norm = float(warm_coarse.norm())
            if not np.isfinite(probe_norm) or probe_norm <= np.finfo(float).tiny:
                raise RuntimeError("live q-space nonzero operator probe collapsed to zero")
            algebraic_transfer = AlgebraicOwnerTransfer(transfer)
            warm_p6 = algebraic_transfer.apply_primal(warm_coarse)
            projected_probe_norm = float(warm_p6.norm())
            if not np.isfinite(projected_probe_norm) or projected_probe_norm <= np.finfo(float).tiny:
                raise RuntimeError("live p6 projection of the q-space probe is zero")

            native_volume = coarse["volume_action"].apply(warm_coarse)
            fine_volume = fine["volume_action"].apply(warm_p6)
            volume_slave_values = np.asarray(fine_volume.array)[
                algebraic_transfer.fine_slaves
            ].copy()
            volume_native_slave_zero = bool(np.all(volume_slave_values == 0.0))

            native_dtn = _new_storage_vector(levels["spaces"][coarse_degree])
            coarse["dtn_action"].apply(warm_coarse, native_dtn)
            fine_dtn = _new_storage_vector(levels["spaces"][6])
            fine["dtn_action"].apply(warm_p6, fine_dtn)
            dtn_slave_values = np.asarray(fine_dtn.array)[
                algebraic_transfer.fine_slaves
            ].copy()
            dtn_native_slave_zero = bool(np.all(dtn_slave_values == 0.0))
            input_owned_slave_zero = bool(
                np.all(probe_input[algebraic_transfer.coarse_slaves] == 0.0)
            )
            input_unchanged = bool(
                np.array_equal(probe_input, np.asarray(warm_coarse.array))
            )
            if not volume_native_slave_zero or not dtn_native_slave_zero:
                aq_projection_check = {
                    "schema": "task039extra.v25.native-aq-projection-check.v1",
                    "reference_free": True,
                    "probe": "deterministic_nonzero_live_coarse_field_strict_slave_zero",
                    "coarse_degree": coarse_degree,
                    "probe_identity": {
                        "input_sha256": _sha256_bytes(
                            np.ascontiguousarray(probe_input).tobytes()
                        ),
                        "owned_slave_zero": input_owned_slave_zero,
                        "owned_slave_count": int(
                            algebraic_transfer.coarse_slaves.size
                        ),
                        "input_unchanged_after_transfer": input_unchanged,
                    },
                    "native_output_slave_zero": {
                        "volume": volume_native_slave_zero,
                        "dtn": dtn_native_slave_zero,
                        "volume_max_abs": float(
                            np.max(np.abs(volume_slave_values))
                            if volume_slave_values.size else 0.0
                        ),
                        "dtn_max_abs": float(
                            np.max(np.abs(dtn_slave_values))
                            if dtn_slave_values.size else 0.0
                        ),
                    },
                    "limit": 1.0e-10,
                    "passed": False,
                    "failure": "native fine operator returned nonzero slave rows",
                    "calls": {
                        "coarse_volume": 1,
                        "fine_volume": 1,
                        "coarse_dtn": 1,
                        "fine_dtn": 1,
                        "transfer_primal": int(algebraic_transfer.primal_count),
                        "transfer_adjoint": 0,
                        "algebraic_wrapper": True,
                    },
                }
                runtime.marker(
                    "v14_common_native_aq_projection_check",
                    aq_projection_check,
                )
                raise RuntimeError(
                    "native fine operator returned nonzero slave rows: "
                    f"{aq_projection_check}"
                )
            # The live native actions already return the algebraic slave-zero
            # dual.  Apply the formal P^H wrapper directly; making a second
            # copy and zeroing it would hide a native slave-row defect.
            projected_volume = algebraic_transfer.apply_adjoint(fine_volume)
            projected_dtn = algebraic_transfer.apply_adjoint(fine_dtn)

            def comparison(native, projected):
                difference = native.duplicate()
                try:
                    native.copy(difference)
                    difference.axpy(PETSc.ScalarType(-1.0), projected)
                    absolute = float(difference.norm())
                    denominator = max(float(native.norm()), np.finfo(float).tiny)
                    relative = absolute / denominator
                finally:
                    difference.destroy()
                if not np.isfinite(relative):
                    raise RuntimeError("nonfinite native/projected q operator identity")
                return {"absolute": absolute, "relative": relative}

            volume_comparison = comparison(native_volume, projected_volume)
            dtn_comparison = comparison(native_dtn, projected_dtn)
            aq_projection_check = {
                "schema": "task039extra.v25.native-aq-projection-check.v1",
                "reference_free": True,
                "probe": "deterministic_nonzero_live_coarse_field_strict_slave_zero",
                "coarse_degree": coarse_degree,
                "space_identity": {
                    "coarse_global_rows": int(levels["spaces"][coarse_degree].dofmap.index_map.size_global),
                    "fine_global_rows": int(levels["spaces"][6].dofmap.index_map.size_global),
                    "coarse_mpc_slave_count": int(len(coarse_floquet.mpc.slaves)),
                    "fine_mpc_slave_count": int(len(levels["floquets"][6].mpc.slaves)),
                    "mode_sha256": str(coarse["mode_sha256"]),
                    "fine_mode_sha256": str(fine["mode_sha256"]),
                },
                "probe_identity": {
                    "input_sha256": _sha256_bytes(np.ascontiguousarray(probe_input).tobytes()),
                    "owned_slave_zero": input_owned_slave_zero,
                    "owned_slave_count": int(algebraic_transfer.coarse_slaves.size),
                    "input_unchanged_after_transfer": input_unchanged,
                },
                "probe_norms": {
                    "coarse": probe_norm,
                    "fine_after_primal_transfer": projected_probe_norm,
                },
                "volume": volume_comparison,
                "dtn": dtn_comparison,
                "native_output_slave_zero": {
                    "volume": volume_native_slave_zero,
                    "dtn": dtn_native_slave_zero,
                    "volume_max_abs": float(
                        np.max(np.abs(volume_slave_values))
                        if volume_slave_values.size else 0.0
                    ),
                    "dtn_max_abs": float(
                        np.max(np.abs(dtn_slave_values))
                        if dtn_slave_values.size else 0.0
                    ),
                },
                "limit": 1.0e-10,
                "passed": bool(
                    input_owned_slave_zero
                    and input_unchanged
                    and volume_native_slave_zero
                    and dtn_native_slave_zero
                    and volume_comparison["relative"] <= 1.0e-10
                    and dtn_comparison["relative"] <= 1.0e-10
                ),
                "native_coarse_operator": "Aq_native",
                "projected_fine_operator": "P^H_A6_native_P",
                "calls": {
                    "coarse_volume": 1,
                    "fine_volume": 1,
                    "coarse_dtn": 1,
                    "fine_dtn": 1,
                    "transfer_primal": 1,
                    "transfer_adjoint": int(algebraic_transfer.adjoint_count),
                    "algebraic_wrapper": True,
                },
            }
            runtime.marker("v14_common_native_aq_projection_check", aq_projection_check)
            if not aq_projection_check["passed"]:
                raise RuntimeError(
                    "native Aq versus projected p6 operator identity failed: "
                    f"{aq_projection_check}"
                )
        else:
            warm_coarse.set(0)
            warm_p6 = transfer.apply_primal(warm_coarse)
        metric.mass(np.zeros(metric.mass.indices.size, dtype=np.complex128))
        metric.curl(np.zeros(metric.curl.indices.size, dtype=np.complex128))
    finally:
        for vector in (
            projected_volume,
            native_dtn,
            projected_dtn,
            fine_dtn,
            warm_p6,
        ):
            if vector is not None:
                vector.destroy()
        warm_coarse.destroy()
    runtime.sample("v14_common_evaluation_warmup")

    def required_int(mapping: Mapping[str, Any], key: str, label: str) -> int:
        value = mapping.get(key)
        if type(value) is not int or value < 0:
            raise RuntimeError(f"{label} is missing a non-negative integer {key}")
        return int(value)

    def audited_numeric_components(owner: Any, prefix: str) -> dict[str, int]:
        audit = getattr(owner, "audit", None)
        if not isinstance(audit, Mapping):
            raise RuntimeError(f"{prefix} has no retained numeric payload audit")
        components = audit.get("retained_numeric_payload_components")
        if not isinstance(components, Mapping):
            raise RuntimeError(f"{prefix} retained numeric payload components are missing")
        # The retained component names are the auditable keys; keep them
        # individually visible in the inventory rather than replacing them
        # with a default total.
        return {
            f"{prefix}_{str(key)}": required_int(components, str(key), prefix)
            for key in components
        }

    def add_component_audit(
        target: dict[str, int], owner: Any, prefix: str
    ) -> None:
        target.update(audited_numeric_components(owner, prefix))

    metric_vector_bytes = sum(
        int(getattr(action.source, "array", np.empty(0)).nbytes)
        + int(getattr(action.target, "array", np.empty(0)).nbytes)
        for action in (metric.mass, metric.curl)
    )
    transfer_audit = dict(transfer.audit)
    routing_costs = dict(getattr(transfer, "routing_costs", {}))
    transfer_audit["routing_costs"] = routing_costs
    transfer_prefix = f"p6{coarse_degree}"
    common_inventory: dict[str, int] = {
        f"{transfer_prefix}_local_cache_bytes": required_int(
            transfer_audit, "local_cache_array_bytes", "P64 transfer audit"
        ),
        f"{transfer_prefix}_owner_plan_bytes": required_int(
            routing_costs, "plan_bytes", "P64 transfer routing audit"
        ),
        f"{transfer_prefix}_owner_apply_extra_bytes": int(
            required_int(
                transfer_audit,
                "owner_operator_adjoint_extra_bytes",
                "P64 transfer audit",
            )
            + required_int(
                transfer_audit,
                "owner_candidate_packet_bytes",
                "P64 transfer audit",
            )
            + required_int(
                transfer_audit,
                "owner_transfer_batch_scratch_bytes",
                "P64 transfer audit",
            )
        ),
        f"{transfer_prefix}_work_vector_bytes": int(
            16
            * (
                int(transfer_audit.get("fine_local_owned_rows", 0))
                + int(transfer_audit.get("coarse_local_owned_rows", 0))
            )
        ),
        "degree6_metric_vector_bytes": metric_vector_bytes,
    }
    for degree, bundle in ((6, fine), (coarse_degree, coarse)):
        volume_action = bundle["volume_action"]
        component_actions = getattr(volume_action, "component_actions", None)
        if not isinstance(component_actions, Mapping):
            raise RuntimeError(f"p{degree} volume action component audit is missing")
        for component_name, action in component_actions.items():
            add_component_audit(
                common_inventory,
                action,
                f"p{degree}_volume_{component_name}",
            )
        dtn_audit = bundle["dtn_action"].audit
        for key in (
            "retained_numeric_bytes_local",
            "retained_identity_bytes",
            "bounded_work_bytes_local",
            "recovery_output_bytes",
        ):
            common_inventory[f"p{degree}_dtn_{key}"] = required_int(
                dtn_audit, key, f"p{degree} DtN audit"
            )
    for component_name, action in metric.actions.items():
        add_component_audit(
            common_inventory,
            action,
            f"degree6_metric_{component_name}",
        )
    # This registration records objects that are already live.  The preceding
    # samples are the RSS gate for their construction; inventory registration
    # must not count the same allocation a second time as a projected RSS.
    runtime.reserve_inventory(
        "common_fixed_caches", common_inventory, check_rss=False
    )
    runtime.marker(
        "v14_common_setup_complete",
        {
            "levels": list(declared_degrees),
            "coarse_degree": coarse_degree,
            "mode_count": len(fine["modes"]),
            "mode_sha256": fine["mode_sha256"],
            "quadrature": quadrature,
            "transfer": transfer_audit,
            "metric": metric.audit,
            "common_inventory": common_inventory,
        },
    )
    return {
        "levels": levels,
        "fine": fine,
        "coarse": coarse,
        # Historical consumers use ``p4`` as the coarse action key.  It is an
        # alias of the requested q action, never a second assembled action.
        "p4": coarse,
        "coarse_degree": coarse_degree,
        "cfg": cfg,
        "quadrature": quadrature,
        "integral_records": integral_records,
        "transfer": transfer,
        "local_transfer": local_transfer,
        "metric": metric,
        "native_aq_projection_check": aq_projection_check,
        "common_inventory_label": "common_fixed_caches",
    }


def _destroy_common(common: dict[str, Any], runtime: _V14Runtime | None = None) -> None:
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        destroy_same_mesh_physical_action,
    )

    metric = common.pop("metric", None)
    if metric is not None:
        metric.destroy()
    transfer = common.pop("transfer", None)
    if transfer is not None:
        transfer.destroy()
    local_transfer = common.pop("local_transfer", None)
    # ``SameMeshHcurlTransfer`` is an immutable NumPy map without a destroy
    # method; the owner wrapper has already dropped its reference to it.
    del local_transfer
    destroyed = set()
    for name in ("coarse", "p4", "fine"):
        bundle = common.pop(name, None)
        if bundle is not None and id(bundle) not in destroyed:
            destroy_same_mesh_physical_action(bundle)
            destroyed.add(id(bundle))
    common.pop("levels", None)
    if runtime is not None:
        runtime.release_inventory(common.pop("common_inventory_label", "common_fixed_caches"))
    gc.collect()


def _release_reviewed_rhs(rhs_records: list[dict[str, Any]] | None) -> None:
    """Drop large reviewed RHS/reference arrays before the common cleanup RSS sample."""

    if rhs_records is None:
        return
    for record in rhs_records:
        for key in ("rhs", "reference_solution", "reference_A4y", "reference_map"):
            record.pop(key, None)
    rhs_records.clear()
    gc.collect()


def _prepare_reviewed_rhs(
    runtime: _V14Runtime,
    common: Mapping[str, Any],
    resolved_payload: Mapping[str, Any],
    root: Path,
    storage_rows: int,
) -> list[dict[str, Any]]:
    """Bind the frozen packets to the freshly rebuilt p4 map and physics."""

    from src.solvers.condensed_fine_reference import native_map_arrays
    from src.solvers.physical_map_identity import compare_native_map_identity

    runtime.marker("v14_reviewed_rhs_loading_started", {})
    records = _load_rhs_and_reference(root, storage_rows)
    current_map = native_map_arrays(
        common["levels"]["spaces"][4], common["levels"]["floquets"][4]
    )
    current_map6 = native_map_arrays(
        common["levels"]["spaces"][6], common["levels"]["floquets"][6]
    )
    identity_records = []
    for item in records:
        reference_map = item["reference_map"]
        map_identity = compare_native_map_identity(
            current_map,
            reference_map,
            context=f"{item['stem']} fresh p4 native constraint map",
        )
        reference_identity = item.get("reference_identity") or {}
        expected_mode = reference_identity.get("mode_sha256")
        expected_physical = reference_identity.get("original_physical_sha256")
        actual_mode = str(common["p4"]["mode_sha256"])
        actual_physical = resolved_payload["provenance"]["physical_model_sha256"]
        if expected_mode is not None and actual_mode != expected_mode:
            raise ValueError(f"{item['stem']} fresh mode identity differs")
        if expected_physical is not None and actual_physical != expected_physical:
            raise ValueError(f"{item['stem']} fresh physical identity differs")
        source = _storage_rhs(common["levels"]["spaces"][4], item["reference_solution"])
        native = source.duplicate()
        try:
            common["p4"]["physical_action"].apply(source, native)
            difference = np.asarray(native.array - item["reference_A4y"], dtype=np.complex128)
            scale = max(float(np.linalg.norm(item["reference_A4y"])), np.finfo(float).tiny)
            a4_relative = float(np.linalg.norm(difference)) / scale
        finally:
            native.destroy()
            source.destroy()
        if a4_relative > 1.0e-10:
            raise ValueError(f"{item['stem']} saved A4y differs from fresh p4 physics")
        identity_records.append(
            {
                "stem": item["stem"],
                "logical_rhs": item["logical_rhs"],
                "calibration_identity": item["calibration_identity"],
                "reference_identity": reference_identity,
                "fresh_physical_model_sha256": actual_physical,
                "fresh_mode_sha256": actual_mode,
                "fresh_p4_map": {
                    key: _jsonable(value) for key, value in current_map.items()
                },
                "fresh_p4_map_identity": map_identity,
                "fresh_p6_map": {
                    key: _jsonable(value) for key, value in current_map6.items()
                },
                "fresh_A4y_relative_to_saved": a4_relative,
            }
        )
    _save_packet(
        runtime.directory,
        "reviewed_rhs_identity",
        {
            "schema": "task039extra.v14.reviewed-rhs-identity.v1",
            "source_sha": runtime.source_sha,
            "rhs_count": len(records),
            "ordered_stems": [item["stem"] for item in records],
            "records": identity_records,
        },
        runtime=runtime,
    )
    runtime.marker(
        "v14_reviewed_rhs_loading_complete",
        {
            "count": len(records),
            "ordered_stems": [item["stem"] for item in records],
            "mode_sha256": common["p4"]["mode_sha256"],
        },
    )
    return records


def _assemble_volume(
    runtime: _V14Runtime,
    common: Mapping[str, Any],
    *,
    inventory_label: str | None = None,
) -> Any:
    import dolfinx_mpc
    from src.solvers.fullspace_v17_p3_oracle import compile_physical_diagnostic_volume

    setup = common["levels"]
    cfg = common["cfg"]
    degree = 4
    runtime.set_phase("assembly")
    runtime.marker("v14_p4_volume_compile_started", {})
    compiled = compile_physical_diagnostic_volume(
        setup, cfg, degree, volume_quadrature_metadata=common["quadrature"]
    )
    floquet = setup["floquets"][degree]
    volume = dolfinx_mpc.cpp.mpc.create_matrix(
        compiled._cpp_object, floquet.mpc._cpp_object, floquet.mpc._cpp_object
    )
    try:
        runtime.sample("p4_volume_pattern")
        dolfinx_mpc.assemble_matrix(compiled, floquet.mpc, bcs=[], A=volume)
        volume.assemble()
        volume_info = volume.getInfo()
        runtime.marker(
            "v14_p4_volume_complete",
            {"size": list(volume.getSize()), "matrix_info": volume_info},
        )
        runtime.sample("p4_volume_complete")
        if inventory_label is not None:
            runtime.check_inventory_projected(
                inventory_label,
                _sparse_payload_bytes(volume_info, int(volume.getSize()[0])),
            )
            runtime.reserve_inventory(
                inventory_label,
                {
                    "matrix_payload_bytes": _sparse_payload_bytes(
                        volume_info, int(volume.getSize()[0])
                    )
                },
                check_rss=False,
            )
        return volume
    except BaseException:
        volume.destroy()
        raise
    finally:
        del compiled


def _new_storage_vector(space: Any) -> Any:
    from dolfinx.la.petsc import create_vector

    return create_vector([(space.dofmap.index_map, space.dofmap.index_map_bs)])


def _sparse_payload_bytes(matrix_info: Mapping[str, Any], rows: int) -> int:
    from petsc4py import PETSc

    nnz = int(matrix_info.get("nz_allocated", 0))
    return (int(rows) + 1) * np.dtype(PETSc.IntType).itemsize + nnz * (
        np.dtype(PETSc.IntType).itemsize + np.dtype(PETSc.ScalarType).itemsize
    )


def _v14_balanced_h6_setup_facts(common: Mapping[str, Any]) -> dict[str, int | str]:
    """Expose the qualified H6 setup estimate without building H6 twice."""

    n6 = int(common["fine"]["dtn_action"].carrier.global_rows)
    n4 = int(common["p4"]["dtn_action"].carrier.global_rows)
    component_actions = common["fine"]["volume_action"].component_actions
    component_payload = sum(
        int(action.audit["retained_numeric_payload_local_bytes"])
        for action in component_actions.values()
    )
    setup_estimate = 2 * component_payload + 12 * n6 * 16
    return {
        "n6": n6,
        "n4": n4,
        "component_payload_bytes": int(component_payload),
        "setup_estimate_bytes": int(setup_estimate),
        "setup_estimate_formula": "2*component_payload+12*n6*16",
    }


def _v14_balanced_apply_workspace_bytes(
    n6: int,
    n4: int,
    kernel_temporary_bytes: int,
    *,
    fine_vector_count: int = 40,
    coarse_vector_count: int = 12,
) -> int:
    """Use the existing BAL workspace formula for a live-size estimate."""

    return int(
        int(fine_vector_count) * int(n6) * 16
        + int(coarse_vector_count) * int(n4) * 16
        + int(kernel_temporary_bytes)
    )


def _v24_p4_prefix_workspace_facts(
    n4: int,
    ntrace: int,
    nport: int,
    *,
    scalar_bytes: int,
    index_bytes: int,
) -> dict[str, Any]:
    """Bound the extra V24 prefix snapshots and diagnostic copies.

    The ordinary BAL_H estimate remains unchanged.  This separate declaration
    covers the opt-in target packet only: one raw plus at most two same-factor
    correction snapshots, followed by one raw or final diagnostic at a time.
    ``ntrace`` is the live condensed full-trace row count and bounds each
    reduced vector without claiming an RSS upper bound.
    """

    n4 = int(n4)
    ntrace = int(ntrace)
    nport = int(nport)
    scalar_bytes = int(scalar_bytes)
    index_bytes = int(index_bytes)
    if min(n4, ntrace, nport, scalar_bytes, index_bytes) <= 0:
        raise ValueError("V24 prefix workspace dimensions must be positive")

    snapshot_count = 3  # raw plus at most two bounded same-factor repairs
    snapshot_field_vectors = 4  # g, correction, native action, native residual
    snapshot_vectors = snapshot_count * (snapshot_field_vectors * n4 + nport)
    snapshot_copy_bytes = snapshot_vectors * scalar_bytes

    diagnostic_count = 2  # raw and final packets are not assumed to overlap
    diagnostic_n4_vectors = 9  # owned rhs/solution, arrays, and recovery copies
    diagnostic_trace_vectors = 4  # reduced rhs/solution/action/residual
    diagnostic_port_vectors = 2  # D*c and H*alpha
    diagnostic_vector_bytes = diagnostic_count * (
        diagnostic_n4_vectors * n4
        + diagnostic_trace_vectors * (ntrace + nport)
        + diagnostic_port_vectors * nport
    ) * scalar_bytes
    diagnostic_index_bytes = diagnostic_count * (
        2 * n4 + 2 * (ntrace + nport)
    ) * index_bytes
    return {
        "n4_storage_rows": n4,
        "ntrace_full_rows": ntrace,
        "nport_rows": nport,
        "scalar_bytes": scalar_bytes,
        "index_bytes": index_bytes,
        "snapshot_count": snapshot_count,
        "snapshot_field_vector_count": snapshot_field_vectors,
        "snapshot_vector_count": snapshot_vectors,
        "snapshot_copy_bytes": int(snapshot_copy_bytes),
        "diagnostic_count": diagnostic_count,
        "diagnostic_n4_vector_count": diagnostic_n4_vectors,
        "diagnostic_trace_vector_count": diagnostic_trace_vectors,
        "diagnostic_port_vector_count": diagnostic_port_vectors,
        "diagnostic_vector_bytes": int(diagnostic_vector_bytes),
        "diagnostic_index_bytes": int(diagnostic_index_bytes),
        "workspace_upper_bytes": int(
            snapshot_copy_bytes + diagnostic_vector_bytes + diagnostic_index_bytes
        ),
        "classification": "derived_conservative_prefix_payload_not_rss_bound",
        "formula": (
            "3*(4*N4+Nport)*scalar + 2*(9*N4+4*(Ntrace+Nport)"
            "+2*Nport)*scalar + 2*(2*N4+2*(Ntrace+Nport))*index"
        ),
    }


def _v14_outer_krylov_workspace_bytes(
    retained_rows: int, *, restart: int = 32
) -> int:
    """Return the existing outer FGMRES vector-pool payload."""

    return max(1, (2 * (int(restart) + 1) + 8) * int(retained_rows) * 16)


def _mumps_memory_observation(facts: Mapping[str, Any]) -> dict[str, Any]:
    raw = facts.get("numeric_raw")
    if not isinstance(raw, Mapping) or not isinstance(raw.get("infog"), Mapping):
        raise RuntimeError("V11 numeric factor did not return MUMPS INFOG")
    infog = raw["infog"]
    values: dict[str, int] = {}
    for key in ("19", "22"):
        value = infog.get(key)
        if type(value) is not int or value < 0:
            raise RuntimeError(f"V11 numeric MUMPS INFOG({key}) is unavailable")
        values[key] = int(value)
    return {
        "unit": "decimal_MB",
        "unit_bytes": 1_000_000,
        "infog19_allocated_mb": values["19"],
        "infog22_used_mb": values["22"],
        "infog19_allocated_bytes_upper": (values["19"] + 1) * 1_000_000,
        "infog22_used_bytes_upper": (values["22"] + 1) * 1_000_000,
        "raw_infog19_and_22": {"19": values["19"], "22": values["22"]},
        "allocation_is_not_inferred_from_icntl23": True,
    }


def _factor_inventory_components(facts: Mapping[str, Any]) -> dict[str, int]:
    rows = int(facts["rows"])
    matrix_info = facts.get("matrix_info_after_factor") or facts["matrix_info_before_factor"]
    request_bytes = int(
        facts["memory_request"]["requested_memory_limit_mb"]
    ) * 1_000_000
    if "numeric_raw" in facts:
        factor_bytes = int(
            _mumps_memory_observation(facts)["infog19_allocated_bytes_upper"]
        )
        factor_key = "factor_infog19_allocated_bytes_upper"
    else:
        factor_bytes = request_bytes
        factor_key = "factor_memory_package_requested_bytes"
    components = {
        "matrix_payload_bytes": _sparse_payload_bytes(matrix_info, rows),
        factor_key: factor_bytes,
    }
    for key, value in dict(facts.get("inventory_components", {})).items():
        components[str(key)] = components.get(str(key), 0) + int(value)
    return components


def _factor_gates(
    runtime: _V14Runtime,
    *,
    local_limit: bool = False,
    matrix_already_reserved: bool = False,
):
    local_cap = int(
        runtime.contract["resources"]["local_factor_matrix_and_allocated_cap_bytes"]
    )
    interface_cap = int(
        runtime.contract["resources"]["interface_matrix_factor_solve_cap_bytes"]
    )

    def before(facts: Mapping[str, Any]) -> None:
        label = str(facts.get("label", ""))
        components = _factor_inventory_components(facts)
        facts["factor_inventory_components"] = dict(components)
        if matrix_already_reserved:
            components["matrix_payload_bytes"] = 0
        matrix_bytes = int(components["matrix_payload_bytes"])
        request_bytes = int(
            components.get(
                "factor_memory_package_requested_bytes",
                components.get("factor_infog19_allocated_bytes_upper", 0),
            )
        )
        if local_limit and label.startswith("internal_") and matrix_bytes + request_bytes > local_cap:
            raise V14ResourceStop(
                "local internal factor matrix+requested allocation exceeds 512MiB"
            )
        if label.startswith("coarse_E") and matrix_bytes + request_bytes > interface_cap:
            raise V14ResourceStop(
                "coarse E matrix+factor+solve allocation exceeds 64MiB"
            )
        runtime.check_inventory_projected(label, sum(components.values()))
        runtime.marker("v14_factor_pre_numeric_gate", dict(facts))
        # The matrix is already resident at this point; only the new factor
        # package and its temporary solve workspace are projected against RSS.
        runtime.check_projected(label, request_bytes)

    def after(facts: Mapping[str, Any]) -> None:
        facts["mumps_memory_observation"] = _mumps_memory_observation(facts)
        complete_components = _factor_inventory_components(facts)
        facts["factor_inventory_components"] = dict(complete_components)
        components = dict(complete_components)
        if matrix_already_reserved:
            components["matrix_payload_bytes"] = 0
        allocated_bytes = int(
            components.get("factor_infog19_allocated_bytes_upper", 0)
        )
        matrix_bytes = int(components.get("matrix_payload_bytes", 0))
        if (
            local_limit
            and str(facts.get("label", "")).startswith("internal_")
            and matrix_bytes + allocated_bytes > local_cap
        ):
            raise V14ResourceStop(
                "local internal factor matrix+INFOG(19) allocation exceeds 512MiB"
            )
        runtime.sample(f"{facts.get('label')}_post_numeric")
        runtime.reserve_inventory(
            str(facts.get("label")),
            components,
            check_rss=False,
        )
        runtime.marker("v14_factor_post_numeric_gate", dict(facts))

    return before, after


def _matrix_residual(matrix: Any, rhs: Any, solution: Any) -> float:
    applied = _matrix_residual_vector(matrix, rhs, solution)
    try:
        denominator = max(float(rhs.norm()), np.finfo(float).tiny)
        value = float(applied.norm()) / denominator
        if not np.isfinite(value):
            raise FloatingPointError("nonfinite explicit matrix residual")
        return value
    finally:
        applied.destroy()


def _matrix_residual_vector(matrix: Any, rhs: Any, solution: Any) -> Any:
    applied = matrix.createVecLeft()
    try:
        matrix.mult(solution, applied)
        applied.axpy(-1.0, rhs)
        return applied
    except BaseException:
        applied.destroy()
        raise


def _physical_residual(action: Any, rhs: Any, solution: Any) -> float:
    applied = solution.duplicate()
    try:
        action.apply(solution, applied)
        applied.axpy(-1.0, rhs)
        denominator = max(float(rhs.norm()), np.finfo(float).tiny)
        value = float(applied.norm()) / denominator
        if not np.isfinite(value):
            raise FloatingPointError("nonfinite native physical residual")
        return value
    finally:
        applied.destroy()


def _physical_residual_decomposition(
    action: Any,
    rhs: Any,
    solution: Any,
    partition: Any,
) -> dict[str, Any]:
    """Evaluate one native A4 residual and split it into I/Gamma pieces."""

    applied = solution.duplicate()
    try:
        action.apply(solution, applied)
        # Keep the exact action output and residual from this one A4 action in
        # the packet.  Callers must bind the displayed decomposition to these
        # arrays rather than reapplying A4 while writing evidence.
        applied_array = np.asarray(applied.array, dtype=np.complex128).copy()
        residual = np.asarray(
            rhs.array - applied_array,
            dtype=np.complex128,
        ).copy()
        denominator = max(
            float(np.linalg.norm(rhs.array)),
            np.finfo(float).tiny,
        )
        active = residual[partition.active_full_indices]
        interface = active[partition.gamma_active_indices]
        internal_parts = [active[block] for block in partition.internal_blocks_active]
        internal = (
            np.concatenate(internal_parts)
            if internal_parts
            else np.empty(0, dtype=np.complex128)
        )
        total_norm = float(np.linalg.norm(residual))
        internal_norm = float(np.linalg.norm(internal))
        interface_norm = float(np.linalg.norm(interface))
        partition_norm = float(np.hypot(internal_norm, interface_norm))
        return {
            "total_absolute_norm": total_norm,
            "total_relative": total_norm / denominator,
            "rhs_norm": float(np.linalg.norm(rhs.array)),
            "applied_array": applied_array,
            "residual_array": residual,
            "internal_absolute_norm": internal_norm,
            "internal_relative": internal_norm / denominator,
            "interface_absolute_norm": interface_norm,
            "interface_relative": interface_norm / denominator,
            "partition_absolute_norm": partition_norm,
            "partition_relative": partition_norm / denominator,
            "partition_residual_pythagorean_relative": abs(
                partition_norm - float(np.linalg.norm(active))
            )
            / max(float(np.linalg.norm(active)), np.finfo(float).tiny),
            "normalization": "full_storage_rhs_norm",
            "native_action_count": 1,
            "finite": bool(
                np.isfinite(total_norm)
                and np.isfinite(internal_norm)
                and np.isfinite(interface_norm)
            ),
        }
    finally:
        applied.destroy()


def _field_metrics(
    runtime: _V14Runtime,
    common: Mapping[str, Any],
    solution_arrays: list[np.ndarray],
    references: list[np.ndarray],
) -> list[dict[str, Any]]:
    from src.solvers.physical_error_diagnostics import metric_square

    runtime.set_phase("evaluation")
    runtime.marker("v14_field_metrics_started", {})
    metric = common["metric"]
    transfer = common["transfer"]
    indices = metric.mass.indices
    result = []
    for solution, reference in zip(solution_arrays, references, strict=True):
        solution_p4 = _storage_rhs(common["levels"]["spaces"][4], solution)
        reference_p4 = _storage_rhs(common["levels"]["spaces"][4], reference)
        solution_p6 = reference_p6 = None
        try:
            solution_p6 = transfer.apply_primal(solution_p4)
            reference_p6 = transfer.apply_primal(reference_p4)
            fine_solution = np.asarray(solution_p6.array[indices], dtype=np.complex128)
            fine_reference = np.asarray(reference_p6.array[indices], dtype=np.complex128)
            delta = fine_solution - fine_reference
            fields = {}
            for name, action in (("L2", metric.mass), ("scaled_curl", metric.curl)):
                error_norm = float(np.sqrt(metric_square(action, delta)))
                reference_norm = float(np.sqrt(metric_square(action, fine_reference)))
                fields[name] = {
                    "absolute_error_norm": error_norm,
                    "reference_norm": reference_norm,
                    "relative": error_norm
                    / max(reference_norm, np.finfo(float).tiny),
                }
            result.append(
                {
                    "field_l2_relative": fields["L2"]["relative"],
                    "scaled_curl_relative": fields["scaled_curl"]["relative"],
                    "fields": fields,
                    "evaluation_space": "P64_primal_to_degree6_independent",
                    "metric_degree": 6,
                    "metric_cell_basis_built": False,
                }
            )
        finally:
            if solution_p6 is not None:
                solution_p6.destroy()
            if reference_p6 is not None:
                reference_p6.destroy()
            solution_p4.destroy()
            reference_p4.destroy()
    runtime.marker(
        "v14_field_metrics_complete",
        {"count": len(result), "metric": metric.audit},
    )
    runtime.sample("field_metrics_complete")
    return result


def _augmented_residual_arrays(
    volume_action: Any,
    physical_action: Any,
    carrier: Any,
    rhs: Any,
    solution: Any,
    port_solution: np.ndarray,
) -> tuple[dict[str, float], np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    native = volume_action.apply(solution)
    native_volume_top = np.asarray(native.array - rhs.array, dtype=np.complex128).copy()
    physical = solution.duplicate()
    try:
        physical_action.apply(solution, physical)
        native_A4_top = np.asarray(
            physical.array - rhs.array, dtype=np.complex128
        ).copy()
    finally:
        physical.destroy()
    augmented_top = native_volume_top.copy()
    for index, entry in enumerate(carrier.entries):
        if len(entry.coupling_rows):
            augmented_top[entry.coupling_rows] += (
                entry.coupling_values * port_solution[index]
            )
    port = np.asarray(
        [
            -np.dot(entry.projection_values, solution.array[entry.projection_rows])
            + entry.normalization_h * port_solution[index]
            for index, entry in enumerate(carrier.entries)
        ],
        dtype=np.complex128,
    )
    denominator = max(float(np.linalg.norm(rhs.array)), np.finfo(float).tiny)
    native_volume_relative = float(np.linalg.norm(native_volume_top)) / denominator
    native_A4_relative = float(np.linalg.norm(native_A4_top)) / denominator
    augmented_top_relative = float(np.linalg.norm(augmented_top)) / denominator
    port_relative = float(np.linalg.norm(port)) / denominator
    total_relative = float(
        np.sqrt(np.vdot(augmented_top, augmented_top).real + np.vdot(port, port).real)
    ) / denominator
    facts = {
        "native_A4_relative": native_A4_relative,
        "native_volume_top_relative": native_volume_relative,
        "augmented_top_relative": augmented_top_relative,
        "port_relative": port_relative,
        "augmented_total_relative": total_relative,
        "native_A4_norm": float(np.linalg.norm(native_A4_top)),
        "rhs_norm": float(np.linalg.norm(rhs.array)),
        "native_volume_top_norm": float(np.linalg.norm(native_volume_top)),
        "augmented_top_norm": float(np.linalg.norm(augmented_top)),
        "port_residual_norm": float(np.linalg.norm(port)),
    }
    return facts, native_A4_top, native_volume_top, augmented_top, port


def _core_action_checks(
    runtime: _V14Runtime,
    core: Any,
    common: Mapping[str, Any],
    storage_template: Any,
) -> dict[str, Any]:
    """Qualify block actions, local backsolves, adjoints and recovery identity."""

    runtime.set_phase("action_checks")
    gamma = core.V_GG.createVecRight()
    gamma_y = gamma.duplicate()
    gamma_mf = gamma.duplicate()
    gamma_explicit = gamma.duplicate()
    gamma_adjoint = gamma.duplicate()
    gamma_adj_explicit = gamma.duplicate()
    interface = core.interface_matrix.createVecRight()
    interface_mf = interface.duplicate()
    interface_explicit = interface.duplicate()
    zero_storage = storage_template.duplicate()
    try:
        gamma.array[:] = np.arange(gamma.getLocalSize(), dtype=np.float64) + 1j * 0.25
        gamma.array[:] /= max(float(gamma.norm()), 1.0)
        gamma_y.array[:] = 1.0 + 1j * np.arange(gamma_y.getLocalSize(), dtype=np.float64)
        gamma_y.array[:] /= max(float(gamma_y.norm()), 1.0)
        core.S_V.mult(gamma, gamma_explicit)
        core.apply_volume_schur(gamma, gamma_mf)
        core.S_V.multHermitian(gamma, gamma_adj_explicit)
        core.apply_volume_schur_adjoint(gamma, gamma_adjoint)
        interface.array[:] = np.arange(interface.getLocalSize(), dtype=np.float64) + 1j * 0.5
        interface.array[:] /= max(float(interface.norm()), 1.0)
        core.interface_matrix.mult(interface, interface_explicit)
        core.apply_interface_matrix_free(interface, interface_mf)

        zero_storage.set(0)
        recovered = core.recover(zero_storage, gamma)
        native_output = recovered.duplicate()
        volume_gamma = gamma.duplicate()
        schur_gamma = gamma.duplicate()
        physical = physical_adjoint = schur_y = adjoint_y = None
        try:
            common["p4"]["physical_action"].apply(recovered, native_output)
            native_gamma = native_output.array[core.partition.gamma_full_indices]
            physical = core.apply_physical_schur(gamma)
            physical_difference = np.linalg.norm(native_gamma - physical.array) / max(
                float(physical.norm()), np.finfo(float).tiny
            )
            physical_adjoint = core.apply_physical_schur_adjoint(gamma)
            expected_adjoint = gamma_adj_explicit.duplicate()
            try:
                expected_adjoint.array[:] = gamma_adj_explicit.array
                for entry in core.port_data:
                    value = np.dot(
                        np.conj(entry["b_values"]), gamma.array[entry["b_gamma"]]
                    ) / np.conj(entry["normalization_h"])
                    expected_adjoint.array[entry["d_gamma"]] += (
                        np.conj(entry["d_values"]) * value
                    )
                physical_adjoint_difference = np.linalg.norm(
                    physical_adjoint.array - expected_adjoint.array
                ) / max(float(expected_adjoint.norm()), np.finfo(float).tiny)
            finally:
                expected_adjoint.destroy()

            # ``g-A4F`` is checked in its internal and Gamma components using
            # the native volume blocks; the carrier contribution is qualified
            # separately by the physical Schur comparison above.
            core.V_GG.mult(gamma, volume_gamma)
            local_backsolve = []
            active_recovered = recovered.array[core.partition.active_full_indices]
            for item in core.internal:
                x_i = np.asarray(active_recovered[item.indices], dtype=np.complex128)
                rhs_i = np.zeros(item.indices.size, dtype=np.complex128)
                if item.gcols.size:
                    rhs_i -= item.A_i_g @ gamma.array[item.gcols]
                x_vec = item.matrix.createVecRight()
                residual_vec = item.matrix.createVecLeft()
                try:
                    x_vec.array[:] = x_i
                    item.matrix.mult(x_vec, residual_vec)
                    residual_vec.array[:] -= rhs_i
                    operation_scale = max(
                        float(np.linalg.norm(rhs_i)),
                        float(np.linalg.norm(residual_vec.array + rhs_i)),
                        np.finfo(float).tiny,
                    )
                    local_backsolve.append(
                        float(residual_vec.norm()) / operation_scale
                    )
                finally:
                    x_vec.destroy()
                    residual_vec.destroy()
                if item.grows.size:
                    volume_gamma.array[item.grows] += item.A_gi @ x_i
            core.S_V.mult(gamma, schur_gamma)
            gamma_decomposition = np.asarray(
                volume_gamma.array - schur_gamma.array, dtype=np.complex128
            )
            decomposition_scale = max(
                float(volume_gamma.norm()),
                float(schur_gamma.norm()),
                float(gamma.norm()),
                np.finfo(float).tiny,
            )
            gamma_decomposition_relative = (
                float(np.linalg.norm(gamma_decomposition)) / decomposition_scale
            )

            schur_y = core.apply_physical_schur(gamma_y)
            adjoint_y = core.apply_physical_schur_adjoint(gamma_y)
            lhs = complex(physical.dot(gamma_y))
            rhs_inner = complex(gamma.dot(adjoint_y))
            inner_scale = max(
                abs(lhs),
                abs(rhs_inner),
                float(physical.norm()) * float(gamma_y.norm()),
                np.finfo(float).tiny,
            )
            adjoint_inner_relative = abs(lhs - rhs_inner) / inner_scale
        finally:
            for value in (native_output, volume_gamma, schur_gamma):
                value.destroy()
            for value in (physical, physical_adjoint, schur_y, adjoint_y):
                if value is not None:
                    value.destroy()
            recovered.destroy()
        facts = {
            "volume_explicit_vs_matrix_free": _vec_relative(gamma_explicit, gamma_mf),
            "volume_adjoint_explicit_vs_matrix_free": _vec_relative(
                gamma_adj_explicit, gamma_adjoint
            ),
            "interface_explicit_vs_matrix_free": _vec_relative(
                interface_explicit, interface_mf
            ),
            "physical_schur_vs_native_carrier": float(physical_difference),
            "physical_schur_adjoint_formula": float(physical_adjoint_difference),
            "local_backsolve_original_matrix_max_relative": max(local_backsolve, default=0.0),
            "g_minus_A4F_internal_relative": max(local_backsolve, default=0.0),
            "g_minus_A4F_gamma_relative": gamma_decomposition_relative,
            "g_minus_A4F_operation_scale": decomposition_scale,
            "physical_schur_complex_inner_product_relative": float(adjoint_inner_relative),
            "factor_solve_counts_after_action_checks": _factor_solve_counts(core),
        }
        limits = {
            "action_bridge": 1.0e-10,
            "physical_schur": 1.0e-10,
            "local_backsolve": 1.0e-10,
            "adjoint_inner_product": 1.0e-10,
            "recovery_decomposition": 1.0e-10,
        }
        facts["limits"] = limits
        facts["passed"] = bool(
            facts["volume_explicit_vs_matrix_free"] <= limits["action_bridge"]
            and facts["volume_adjoint_explicit_vs_matrix_free"] <= limits["action_bridge"]
            and facts["interface_explicit_vs_matrix_free"] <= limits["action_bridge"]
            and facts["physical_schur_vs_native_carrier"] <= limits["physical_schur"]
            and facts["physical_schur_adjoint_formula"] <= limits["physical_schur"]
            and facts["local_backsolve_original_matrix_max_relative"] <= limits["local_backsolve"]
            and facts["g_minus_A4F_gamma_relative"] <= limits["recovery_decomposition"]
            and facts["physical_schur_complex_inner_product_relative"] <= limits["adjoint_inner_product"]
        )
        runtime.marker("v14_action_checks_complete", facts)
        runtime.sample("q2_action_checks_complete")
        return facts
    finally:
        for value in (
            gamma,
            gamma_y,
            gamma_mf,
            gamma_explicit,
            gamma_adjoint,
            gamma_adj_explicit,
            interface,
            interface_mf,
            interface_explicit,
            zero_storage,
        ):
            value.destroy()


def _vec_relative(left: Any, right: Any) -> float:
    difference = left.copy()
    try:
        difference.axpy(-1.0, right)
        return float(difference.norm()) / max(float(right.norm()), np.finfo(float).tiny)
    finally:
        difference.destroy()


def _factor_solve_counts(core: Any) -> dict[str, Any]:
    return {
        "internal": [int(getattr(item.factor, "solve_calls", 0)) for item in core.internal],
        "interface": None
        if core.interface_factor is None
        else int(getattr(core.interface_factor, "solve_calls", 0)),
        "internal_total": int(
            sum(int(getattr(item.factor, "solve_calls", 0)) for item in core.internal)
        ),
    }


def _q1_residual_arrays(
    common: Mapping[str, Any],
    reviewed: Mapping[str, Any],
    solution: Any,
    storage_rows: int,
) -> tuple[dict[str, float], np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    storage = _storage_rhs(
        common["levels"]["spaces"][4], solution.array[:storage_rows]
    )
    rhs = _storage_rhs(common["levels"]["spaces"][4], reviewed["rhs"])
    try:
        return _augmented_residual_arrays(
            common["p4"]["volume_action"],
            common["p4"]["physical_action"],
            common["p4"]["dtn_action"].carrier,
            rhs,
            storage,
            np.asarray(solution.array[storage_rows:], dtype=np.complex128),
        )
    finally:
        storage.destroy()
        rhs.destroy()


def _q1_full_direct(
    runtime: _V14Runtime,
    common: dict[str, Any],
    rhs_records: list[dict[str, Any]],
) -> dict[str, Any]:
    from src.solvers.fullspace_p4_reference import build_reference_matrix
    from src.solvers.fullspace_v17_p3_oracle import _MumpsFactor
    from src.solvers.physical_interface_schur import _prepare_factor

    storage_rows = int(common["p4"]["dtn_action"].carrier.global_rows)
    if storage_rows != 53084:
        raise ValueError(f"V14 p4 carrier storage rows changed: {storage_rows}")
    workspace_label = "q1_augmentation_workspace"
    matrix = None
    factor = None
    factor_facts = None
    solutions: list[np.ndarray] = []
    solve_records: list[dict[str, Any]] = []

    def allocation_callback(facts: Mapping[str, Any]) -> None:
        volume_bytes = _sparse_payload_bytes(
            {"nz_allocated": facts["volume_nnz"]}, int(facts["volume_rows"])
        )
        augmented_bytes = int(facts["matrix_payload_bytes"])
        workspace = min(
            int(runtime.workspace_cap),
            16 * (int(facts["volume_rows"]) + int(facts["port_rows"])) * 16,
        )
        runtime.check_inventory_projected(
            "q1_augmented_matrix", volume_bytes + augmented_bytes
        )
        runtime.check_projected(
            "q1_augmented_matrix", augmented_bytes, workspace_bytes=workspace
        )
        runtime.reserve_workspace(workspace_label, workspace)

    runtime.set_phase("assembly")
    matrix, matrix_facts = build_reference_matrix(
        common["levels"],
        common["cfg"],
        common["p4"],
        common["quadrature"],
        marker=runtime.marker,
        sample=lambda: runtime.sample("q1_assembly"),
        degree=4,
        allocation_callback=allocation_callback,
    )
    runtime.release_workspace(workspace_label)
    before, after = _factor_gates(runtime)
    try:
        runtime.set_phase("factor")
        factor, factor_facts = _prepare_factor(
            matrix,
            _MumpsFactor,
            label="q1_full_global",
            resource_sample=lambda: runtime.sample("q1_factor"),
            marker=runtime.marker,
            pre_numeric_gate=before,
            post_numeric_gate=after,
        )
        for reviewed in rhs_records:
            runtime.set_phase("solve")
            runtime.marker("q1_rhs_solve_started", {"stem": reviewed["stem"]})
            started = time.perf_counter()
            rhs = matrix.createVecRight()
            rhs.set(0)
            rhs.array[:storage_rows] = reviewed["rhs"]
            solution = matrix.createVecRight()
            residual_vector = None
            try:
                solve_before = int(getattr(factor, "solve_calls", 0))
                factor.solve_repeated(rhs, solution)
                refinements = []
                for refinement_index in range(3):
                    if residual_vector is not None:
                        residual_vector.destroy()
                    residual_vector = _matrix_residual_vector(matrix, rhs, solution)
                    facts, native_A4, native_volume, augmented_top, port = _q1_residual_arrays(
                        common, reviewed, solution, storage_rows
                    )
                    if facts["native_A4_relative"] <= 1.0e-10:
                        break
                    if refinement_index == 2:
                        break
                    refine_started = time.perf_counter()
                    count_before = int(getattr(factor, "solve_calls", 0))
                    correction = matrix.createVecRight()
                    try:
                        factor.solve_repeated(residual_vector, correction)
                        solution.axpy(-1.0, correction)
                    finally:
                        correction.destroy()
                    refinements.append(
                        {
                            "index": refinement_index + 1,
                            "elapsed_seconds": time.perf_counter() - refine_started,
                            "factor_solve_calls_before": count_before,
                            "factor_solve_calls_after": int(getattr(factor, "solve_calls", 0)),
                            "trigger": "native_augmented_residual_above_1e-10",
                        }
                    )
                if residual_vector is None:
                    residual_vector = _matrix_residual_vector(matrix, rhs, solution)
                facts, native_A4, native_volume, augmented_top, port = _q1_residual_arrays(
                    common, reviewed, solution, storage_rows
                )
                solution_array = np.asarray(solution.array[:storage_rows]).copy()
                solutions.append(solution_array)
                solve_after = int(getattr(factor, "solve_calls", 0))
                solve_record = {
                    "stem": reviewed["stem"],
                    "elapsed_seconds": time.perf_counter() - started,
                    "matrix_relative_residual": float(residual_vector.norm())
                    / max(float(rhs.norm()), np.finfo(float).tiny),
                    "augmented_residual": facts,
                    "native_A4_relative_residual": facts["native_A4_relative"],
                    "native_volume_top_relative_residual": facts["native_volume_top_relative"],
                    "augmented_top_relative_residual": facts["augmented_top_relative"],
                    "augmented_total_relative_residual": facts["augmented_total_relative"],
                    "factor_solve_calls_before": solve_before,
                    "factor_solve_calls_after": solve_after,
                    "factor_solve_call_delta": solve_after - solve_before,
                    "refinements": refinements,
                    "solution_sha256": _sha256_bytes(
                        np.ascontiguousarray(solution_array).tobytes()
                    ),
                }
                packet = _save_packet(
                    runtime.directory / "q1_rhs_packets",
                    reviewed["stem"],
                    {
                        "schema": "task039extra.v14.q1-rhs-packet.v1",
                        "identity": {
                            key: value
                            for key, value in reviewed.items()
                            if key
                            not in {
                                "rhs",
                                "reference_solution",
                                "reference_A4y",
                                "reference_map",
                            }
                        },
                        "solve": solve_record,
                        "x_augmented": np.asarray(solution.array).copy(),
                        "x_storage": solution_array,
                        "matrix_residual": np.asarray(residual_vector.array).copy(),
                        "native_A4_residual": native_A4,
                        "native_volume_top_residual": native_volume,
                        "augmented_top_residual": augmented_top,
                        "port_residual": port,
                    },
                    runtime=runtime,
                )
                solve_record["packet"] = packet
                solve_records.append(solve_record)
            except BaseException as exc:
                _save_packet(
                    runtime.directory / "q1_rhs_packets",
                    reviewed["stem"] + "_failure",
                    {
                        "schema": "task039extra.v14.q1-rhs-failure-packet.v1",
                        "identity": {
                            key: value
                            for key, value in reviewed.items()
                            if key
                            not in {
                                "rhs",
                                "reference_solution",
                                "reference_A4y",
                                "reference_map",
                            }
                        },
                        "error": {"type": type(exc).__name__, "message": str(exc)},
                        "factor_solve_calls": int(getattr(factor, "solve_calls", 0)),
                    },
                    runtime=runtime,
                )
                raise
            finally:
                if residual_vector is not None:
                    residual_vector.destroy()
                rhs.destroy()
                solution.destroy()
            runtime.sample(f"q1_rhs_{reviewed['stem']}_complete")
        field = _field_metrics(
            runtime,
            common,
            solutions,
            [item["reference_solution"] for item in rhs_records],
        )
        for solve, field_record, reviewed in zip(
            solve_records, field, rhs_records, strict=True
        ):
            solve["field_metrics"] = field_record
            solve["reference_true_residual"] = reviewed["reference_true_residual"]
        max_matrix = max(item["matrix_relative_residual"] for item in solve_records)
        max_native_A4 = max(item["native_A4_relative_residual"] for item in solve_records)
        max_augmented = max(
            item["augmented_total_relative_residual"] for item in solve_records
        )
        max_field = max(
            max(
                item["field_metrics"]["field_l2_relative"],
                item["field_metrics"]["scaled_curl_relative"],
            )
            for item in solve_records
        )
        # Review V14's numerical admission line is the original native A4
        # residual.  The assembled-matrix and augmented-vector residuals are
        # retained as diagnostics for investigating construction errors, but
        # they are not promoted to a second independent precision gate.
        exact_pass = max_native_A4 <= 1.0e-10
        field_pass = max_field <= 1.0e-8
        record = {
            "schema": "task039extra.v14.q1-full-direct.v2",
            "status": "Q1_FULL_DIRECT_PASS"
            if exact_pass and field_pass
            else "EXACT_CONTROL_UNQUALIFIED",
            "official_result": bool(exact_pass and field_pass),
            "rhs": [
                {
                    key: value
                    for key, value in item.items()
                    if key
                    not in {
                        "rhs",
                        "reference_solution",
                        "reference_A4y",
                        "reference_map",
                    }
                }
                for item in rhs_records
            ],
            "matrix": {**matrix_facts, "matrix_info": matrix.getInfo()},
            "factor": factor_facts,
            "solve_records": solve_records,
            "gates": {
                "native_A4_relative_residual": 1.0e-10,
                "field_l2_and_scaled_curl": 1.0e-8,
                "admission_basis": "original_A4_and_P64_field_metrics",
                "max_matrix_relative_residual": max_matrix,
                "max_native_A4_relative_residual": max_native_A4,
                "max_augmented_total_relative_residual": max_augmented,
                "matrix_and_augmented_residuals_are_diagnostics_only": True,
                "max_field_l2_or_scaled_curl": max_field,
            },
            "lifecycle": {
                "factor_count": 1,
                "factor_solve_count": int(getattr(factor, "solve_calls", 0)),
                "sequential_rhs": True,
                "factor_live_through_all_rhs_and_metrics": True,
            },
        }
        runtime.marker("q1_full_direct_complete", record)
        return record
    finally:
        runtime.release_workspace(workspace_label)
        if factor is not None:
            factor.destroy()
            runtime.release_inventory("q1_full_global")
        if matrix is not None:
            matrix.destroy()


def _storage_rhs(space: Any, values: np.ndarray) -> Any:
    result = _new_storage_vector(space)
    result.array[:] = values
    return result


def _save_atomic_npz(path: Path, arrays: Mapping[str, Any]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as stream:
        np.savez(stream, **arrays)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _save_petsc_binary(path: Path, matrix: Any) -> None:
    from petsc4py import PETSc

    temporary = path.with_name(path.name + ".tmp")
    viewer = PETSc.Viewer().createBinary(
        str(temporary), "w", comm=matrix.getComm()
    )
    try:
        matrix.view(viewer)
        viewer.flush()
    finally:
        viewer.destroy()
    os.replace(temporary, path)


def _q2_state_artifact(
    runtime: _V14Runtime,
    root: Path,
    relative_path: str,
    writer: Any,
    *,
    workspace_bytes: int = 17 << 20,
) -> dict[str, Any]:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    label = f"q2_state_{path.name}"
    runtime.reserve_workspace(label, int(workspace_bytes))
    try:
        writer(path)
        # The hash is part of the same bounded save operation: the existing
        # chunked helper uses a 1 MiB streaming read buffer.
        descriptor = {
            "path": str(path),
            "relative_path": str(path.relative_to(root)),
            "bytes": int(path.stat().st_size),
            "sha256": _sha256_file(path),
        }
    finally:
        runtime.release_workspace(label)
    return descriptor


def _factor_count_delta(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    internal = [
        int(right) - int(left)
        for left, right in zip(before["internal"], after["internal"], strict=True)
    ]
    interface = None
    if before.get("interface") is not None and after.get("interface") is not None:
        interface = int(after["interface"]) - int(before["interface"])
    return {
        "internal": internal,
        "interface": interface,
        "internal_total": int(sum(internal)),
    }


def _q2_interface_residual(
    core: Any,
    rhs: Any,
    interface_solution: np.ndarray,
) -> dict[str, Any]:
    started = time.perf_counter()
    reduced, port_rhs = core.reduce(rhs)
    interface_rhs = np.concatenate((reduced, port_rhs))
    interface_vector = core.interface_matrix.createVecRight()
    interface_applied = core.interface_matrix.createVecLeft()
    try:
        interface_vector.array[:] = interface_solution
        core.interface_matrix.mult(interface_vector, interface_applied)
        residual = np.asarray(
            interface_applied.array - interface_rhs, dtype=np.complex128
        ).copy()
    finally:
        interface_vector.destroy()
        interface_applied.destroy()
    original_rhs_norm = max(float(rhs.norm()), np.finfo(float).tiny)
    reduced_rhs_norm = max(float(np.linalg.norm(interface_rhs)), np.finfo(float).tiny)
    residual_norm = float(np.linalg.norm(residual))
    return {
        "reduced_rhs": np.asarray(reduced).copy(),
        "port_rhs": np.asarray(port_rhs).copy(),
        "interface_rhs": interface_rhs,
        "interface_residual": residual,
        # The first value is the only interface residual reported on the
        # original-RHS scale.  The reduced-RHS normalization is useful for
        # conditioning/debugging but is explicitly diagnostic rather than an
        # additional Review V14 admission gate.
        "original_rhs_norm": original_rhs_norm,
        "reduced_rhs_norm": reduced_rhs_norm,
        "interface_residual_norm": residual_norm,
        "interface_relative_residual": residual_norm / original_rhs_norm,
        "interface_relative_residual_original_rhs": residual_norm / original_rhs_norm,
        "interface_reduced_rhs_relative_residual": residual_norm / reduced_rhs_norm,
        "interface_residual_normalization": "original_storage_rhs_norm",
        "interface_reduced_rhs_normalization": "reduced_rhs_norm_diagnostic_only",
        "elapsed_seconds": time.perf_counter() - started,
    }


def _q2_residual_arrays(
    common: Mapping[str, Any],
    reviewed: Mapping[str, Any],
    solution: Any,
    interface_solution: np.ndarray,
    gamma_rows: int,
) -> tuple[dict[str, float], np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    interface_solution = np.asarray(interface_solution, dtype=np.complex128)
    port_count = len(common["p4"]["dtn_action"].carrier.entries)
    if interface_solution.size != int(gamma_rows) + port_count:
        raise ValueError("Q2 interface solution has an unexpected Gamma/port layout")
    rhs = _storage_rhs(common["levels"]["spaces"][4], reviewed["rhs"])
    try:
        return _augmented_residual_arrays(
            common["p4"]["volume_action"],
            common["p4"]["physical_action"],
            common["p4"]["dtn_action"].carrier,
            rhs,
            solution,
            interface_solution[int(gamma_rows) :],
        )
    finally:
        rhs.destroy()


def _q2_reusable_state(runtime: _V14Runtime, core: Any) -> dict[str, Any]:
    """Persist the Q2 core incrementally without a global in-memory copy."""

    state_root = runtime.directory / "q2_reusable_state"
    state_root.mkdir(parents=True, exist_ok=True)
    artifacts: list[dict[str, Any]] = []

    def add(path: Path, kind: str, **facts: Any) -> None:
        artifacts.append({"kind": kind, **facts, "artifact": _jsonable(path)})

    runtime.marker("q2_reusable_state_save_started", {})
    partition_arrays: dict[str, Any] = {
        "active_full_indices": core.partition.active_full_indices,
        "slave_full_indices": core.partition.slave_full_indices,
        "gamma_full_indices": core.partition.gamma_full_indices,
        "gamma_active_indices": core.partition.gamma_active_indices,
        "port_support_full_indices": core.partition.port_support_full_indices,
    }
    for index, block in enumerate(core.partition.internal_blocks_full):
        partition_arrays[f"internal_block_{index}_full"] = block
        partition_arrays[f"internal_block_{index}_active"] = (
            core.partition.internal_blocks_active[index]
        )
    partition_path = _q2_state_artifact(
        runtime,
        runtime.directory,
        "q2_reusable_state/partition.npz",
        lambda path, arrays=partition_arrays: _save_atomic_npz(path, arrays),
    )
    add(Path(partition_path["path"]), "partition_arrays", descriptor=partition_path)
    del partition_arrays

    for name, matrix in (("S_V", core.S_V), ("V_GG", core.V_GG)):
        descriptor = _q2_state_artifact(
            runtime,
            runtime.directory,
            f"q2_reusable_state/{name}.petscbin",
            lambda path, matrix=matrix: _save_petsc_binary(path, matrix),
        )
        add(
            Path(descriptor["path"]),
            "petsc_matrix",
            name=name,
            shape=[int(value) for value in matrix.getSize()],
            matrix_info=matrix.getInfo(),
            descriptor=descriptor,
        )

    port_arrays: dict[str, Any] = {}
    for index, entry in enumerate(core.port_data):
        for key in ("b_gamma", "b_values", "b_full", "d_gamma", "d_values", "d_full"):
            port_arrays[f"port_{index:03d}_{key}"] = entry[key]
        port_arrays[f"port_{index:03d}_normalization_h"] = np.asarray(
            [entry["normalization_h"]], dtype=np.complex128
        )
    port_descriptor = _q2_state_artifact(
        runtime,
        runtime.directory,
        "q2_reusable_state/port_data.npz",
        lambda path, arrays=port_arrays: _save_atomic_npz(path, arrays),
    )
    add(
        Path(port_descriptor["path"]),
        "port_arrays",
        port_count=len(core.port_data),
        descriptor=port_descriptor,
    )
    del port_arrays

    internal_descriptors = []
    factor_records = list(core.factor_facts.get("internal", []))
    for index, item in enumerate(core.internal):
        coupling_arrays = {
            "indices": item.indices,
            "grows": item.grows,
            "gcols": item.gcols,
            "A_gi": item.A_gi,
            "A_i_g": item.A_i_g,
        }
        coupling_descriptor = _q2_state_artifact(
            runtime,
            runtime.directory,
            f"q2_reusable_state/internal_{index:02d}_coupling.npz",
            lambda path, arrays=coupling_arrays: _save_atomic_npz(path, arrays),
        )
        del coupling_arrays
        matrix_descriptor = _q2_state_artifact(
            runtime,
            runtime.directory,
            f"q2_reusable_state/internal_{index:02d}.petscbin",
            lambda path, matrix=item.matrix: _save_petsc_binary(path, matrix),
        )
        factor_record = factor_records[index] if index < len(factor_records) else {}
        metadata = {
            "schema": "task039extra.v14.q2-internal-state.v1",
            "block_index": int(item.block_index),
            "rows": int(item.indices.size),
            "grows": int(item.grows.size),
            "gcols": int(item.gcols.size),
            "factor_solve_calls_at_build": int(item.solve_calls_at_build),
            "factor": factor_record,
            "coupling": coupling_descriptor,
            "matrix": matrix_descriptor,
        }
        metadata_descriptor = _q2_state_artifact(
            runtime,
            runtime.directory,
            f"q2_reusable_state/internal_{index:02d}.json",
            lambda path, metadata=metadata: _write_json(path, metadata),
            workspace_bytes=1 << 20,
        )
        internal_descriptors.append(metadata_descriptor)
        add(
            Path(metadata_descriptor["path"]),
            "internal_block_metadata",
            block_index=index,
            descriptor=metadata_descriptor,
        )

    state = {
        "schema": "task039extra.v14.q2-reusable-core-state.v2",
        "source_sha": runtime.source_sha,
        "partition": core.partition.audit(),
        "internal_block_count": len(core.internal),
        "artifacts": artifacts,
        "internal_metadata": internal_descriptors,
        "omitted": [
            "interface_matrix",
            "global_interface_factor",
            "numeric_interface_solution",
        ],
        "factor_facts_summary": {
            "S_V": core.factor_facts.get("S_V"),
            "interface": {
                "rows": core.factor_facts.get("interface", {}).get("rows"),
                "matrix_info": core.factor_facts.get("interface", {}).get(
                    "matrix_info"
                ),
                "not_saved": True,
            },
        },
    }
    index_path = state_root / "index.json"
    runtime.reserve_workspace("q2_state_index", 1 << 20)
    try:
        _write_json(index_path, state)
        index_sha = _sha256_file(index_path)
    finally:
        runtime.release_workspace("q2_state_index")
    state["index"] = {
        "path": str(index_path),
        "relative_path": str(index_path.relative_to(runtime.directory)),
        "bytes": int(index_path.stat().st_size),
        "sha256": index_sha,
    }
    runtime.marker("q2_reusable_state_save_complete", state["index"])
    return state


def _q2_reference_elimination_checks(
    runtime: _V14Runtime,
    core: Any,
    common: Mapping[str, Any],
    rhs_records: list[dict[str, Any]],
    storage_template: Any,
) -> dict[str, Any]:
    """Check the existing ``g, y, A4y`` packets against the fresh Schur core."""

    gamma_full = core.partition.gamma_full_indices
    gamma_active = core.partition.gamma_active_indices
    records: list[dict[str, Any]] = []
    for reviewed in rhs_records:
        started = time.perf_counter()
        rhs = storage_template.copy()
        rhs.array[:] = reviewed["rhs"]
        reference_y = np.asarray(reviewed["reference_solution"], dtype=np.complex128)
        reference_A4y = np.asarray(reviewed["reference_A4y"], dtype=np.complex128)
        try:
            rhs_norm = float(np.linalg.norm(reviewed["rhs"]))
            counts_before = _factor_solve_counts(core)
            elimination_started = time.perf_counter()
            f_gamma, _port_rhs = core.reduce(rhs)
            elimination_seconds = time.perf_counter() - elimination_started
            elimination_after = _factor_solve_counts(core)

            y_gamma = core.V_GG.createVecRight()
            volume_schur_y = core.S_V.createVecLeft()
            try:
                y_gamma.array[:] = reference_y[gamma_full]
                core.S_V.mult(y_gamma, volume_schur_y)
                physical_schur_array = np.asarray(
                    volume_schur_y.array, dtype=np.complex128
                ).copy()
                for entry in core.port_data:
                    h = entry["normalization_h"]
                    if h == 0:
                        raise ZeroDivisionError("reference port normalization H is zero")
                    alpha = np.dot(
                        entry["d_values"], reference_y[entry["d_full"]]
                    ) / h
                    physical_schur_array[entry["b_gamma"]] += (
                        entry["b_values"] * alpha
                    )
                expected_gamma = np.asarray(
                    f_gamma - physical_schur_array, dtype=np.complex128
                ).copy()
            finally:
                volume_schur_y.destroy()
                y_gamma.destroy()

            active_rhs = np.asarray(
                reviewed["rhs"][core.partition.active_full_indices],
                dtype=np.complex128,
            )
            active_reference = np.asarray(
                reference_y[core.partition.active_full_indices],
                dtype=np.complex128,
            )
            local_records: list[dict[str, Any]] = []
            recovery_started = time.perf_counter()
            recovered_result, recovery_facts = core.recover(
                rhs,
                np.asarray(reference_y[gamma_full], dtype=np.complex128),
                return_facts=True,
            )
            recovery_seconds = time.perf_counter() - recovery_started
            counts_after = _factor_solve_counts(core)
            try:
                recovered_active = np.asarray(
                    recovered_result.array[core.partition.active_full_indices],
                    dtype=np.complex128,
                ).copy()
                for item in core.internal:
                    local_rhs = active_rhs[item.indices].copy()
                    if item.gcols.size:
                        local_rhs -= item.A_i_g @ recovered_active[
                            gamma_active[item.gcols]
                        ]
                    recovered_local = recovered_active[item.indices]
                    local_residual = item.matrix.createVecLeft()
                    local_vector = item.matrix.createVecRight()
                    try:
                        local_vector.array[:] = recovered_local
                        item.matrix.mult(local_vector, local_residual)
                        local_residual.array[:] -= local_rhs
                        local_scale = max(
                            float(np.linalg.norm(local_rhs)),
                            float(np.linalg.norm(local_residual.array + local_rhs)),
                            np.finfo(float).tiny,
                        )
                        local_records.append(
                            {
                                "block_index": int(item.block_index),
                                "rows": int(item.indices.size),
                                "relative_residual": float(local_residual.norm())
                                / local_scale,
                                "reference_difference_relative": float(
                                    np.linalg.norm(
                                        recovered_local - active_reference[item.indices]
                                    )
                                )
                                / max(
                                    float(np.linalg.norm(active_reference[item.indices])),
                                    np.finfo(float).tiny,
                                ),
                            }
                        )
                    finally:
                        local_vector.destroy()
                        local_residual.destroy()
            finally:
                recovered_result.destroy()

            g_minus_A4y = np.asarray(
                reviewed["rhs"] - reference_A4y, dtype=np.complex128
            ).copy()
            expected_identity = np.zeros(storage_template.getLocalSize(), dtype=np.complex128)
            expected_identity[gamma_full] = expected_gamma
            identity_difference = g_minus_A4y - expected_identity
            internal_identity = g_minus_A4y[core.partition.internal_blocks_full[0]]
            for block in core.partition.internal_blocks_full[1:]:
                internal_identity = np.concatenate(
                    (internal_identity, g_minus_A4y[block])
                )
            max_local_residual = max(
                (item["relative_residual"] for item in local_records),
                default=0.0,
            )
            max_reference_difference = max(
                (item["reference_difference_relative"] for item in local_records),
                default=0.0,
            )
            identity_relative = float(np.linalg.norm(identity_difference)) / max(
                rhs_norm, np.finfo(float).tiny
            )
            internal_zero_relative = float(np.linalg.norm(internal_identity)) / max(
                rhs_norm, np.finfo(float).tiny
            )
            gamma_identity_relative = float(
                np.linalg.norm(g_minus_A4y[gamma_full] - expected_gamma)
            ) / max(rhs_norm, np.finfo(float).tiny)
            counts_after = _factor_solve_counts(core)
            facts = {
                "stem": reviewed["stem"],
                "logical_rhs": reviewed["logical_rhs"],
                "rhs_sha256": reviewed["g_sha256"],
                "reference_solution_sha256": _sha256_bytes(reference_y.tobytes()),
                "reference_A4y_sha256": _sha256_bytes(reference_A4y.tobytes()),
                "rhs_norm": rhs_norm,
                "elimination_seconds": elimination_seconds,
                "recovery_seconds": recovery_seconds,
                "factor_solve_counts_before": counts_before,
                "factor_solve_counts_after_elimination": elimination_after,
                "factor_solve_counts_after_recovery": counts_after,
                "factor_solve_call_delta_elimination": _factor_count_delta(
                    counts_before, elimination_after
                ),
                "factor_solve_call_delta_recovery": _factor_count_delta(
                    elimination_after, counts_after
                ),
                "recovery_facts": recovery_facts,
                "internal_block_count": len(core.internal),
                "internal_recovery_records": local_records,
                "internal_zero_relative": internal_zero_relative,
                "gamma_identity_relative": gamma_identity_relative,
                "full_identity_relative": identity_relative,
                "max_local_recovery_residual": max_local_residual,
                "max_reference_internal_difference": max_reference_difference,
                "elapsed_seconds": time.perf_counter() - started,
                "limits": {
                    "internal_zero_relative": 1.0e-10,
                    "gamma_identity_relative": 1.0e-10,
                    "full_identity_relative": 1.0e-10,
                    "local_recovery_residual": 1.0e-10,
                },
            }
            facts["passed"] = bool(
                facts["internal_zero_relative"] <= facts["limits"]["internal_zero_relative"]
                and facts["gamma_identity_relative"]
                <= facts["limits"]["gamma_identity_relative"]
                and facts["full_identity_relative"]
                <= facts["limits"]["full_identity_relative"]
                and facts["max_local_recovery_residual"]
                <= facts["limits"]["local_recovery_residual"]
                and facts["factor_solve_call_delta_elimination"]["internal_total"]
                == len(core.internal)
                and facts["factor_solve_call_delta_recovery"]["internal_total"]
                == len(core.internal)
            )
            _save_packet(
                runtime.directory / "q2_reference_elimination",
                reviewed["stem"],
                {
                    "schema": "task039extra.v14.q2-reference-elimination-packet.v1",
                    "facts": facts,
                    "g_minus_A4y": g_minus_A4y,
                    "expected_identity": expected_identity,
                    "identity_difference": identity_difference,
                    "reference_y": reference_y,
                    "reference_A4y": reference_A4y,
                    "recovered_active": recovered_active,
                },
                runtime=runtime,
            )
            records.append(facts)
            if not facts["passed"]:
                raise RuntimeError(
                    f"V14 reviewed reference elimination identity failed: {facts}"
                )
        finally:
            rhs.destroy()
    return {
        "schema": "task039extra.v14.q2-reference-elimination.v1",
        "records": records,
        "rhs_count": len(records),
        "passed": len(records) == len(rhs_records) and all(
            record["passed"] for record in records
        ),
    }


def _q2_schur_direct(
    runtime: _V14Runtime,
    common: dict[str, Any],
    rhs_records: list[dict[str, Any]],
) -> dict[str, Any]:
    from src.solvers.physical_interface_schur import (
        _submatrix,
        build_interface_partition,
        build_physical_interface_schur,
        factorize_interface_schur,
    )

    storage_rows = int(common["p4"]["dtn_action"].carrier.global_rows)
    if storage_rows != 53084:
        raise ValueError(f"V14 p4 carrier storage rows changed: {storage_rows}")
    full_volume = None
    active_volume = None
    storage_template = None
    core = None
    last_rhs = None
    last_gamma = None
    reserved_labels: set[str] = set()
    reserved_workspaces: set[str] = set()
    volume_facts: dict[str, Any] = {}
    state = None
    try:
        carrier = common["p4"]["dtn_action"].carrier
        runtime.set_phase("assembly")
        full_volume = _assemble_volume(
            runtime, common, inventory_label="q2_full_volume"
        )
        partition, port_data = build_interface_partition(
            common["levels"]["spaces"][4],
            common["levels"]["floquets"][4],
            carrier,
            volume=full_volume,
        )
        runtime.marker("q2_partition_complete", partition.audit())
        full_info = full_volume.getInfo()
        full_rows = int(full_volume.getSize()[0])
        full_payload = _sparse_payload_bytes(full_info, full_rows)
        active_upper_label = "q2_active_volume"
        runtime.check_projected(active_upper_label, full_payload)
        runtime.reserve_inventory(
            active_upper_label,
            {"matrix_payload_upper_bytes": full_payload},
            check_rss=False,
        )
        reserved_labels.add(active_upper_label)
        storage_template = full_volume.createVecRight()
        active_volume = _submatrix(full_volume, partition.active_full_indices)
        active_info = active_volume.getInfo()
        active_rows = int(active_volume.getSize()[0])
        active_payload = _sparse_payload_bytes(active_info, active_rows)
        runtime.replace_inventory(
            active_upper_label,
            {"matrix_payload_bytes": active_payload},
        )
        full_volume.destroy()
        full_volume = None
        runtime.release_inventory("q2_full_volume")
        volume_facts = {
            "full_storage_rows": full_rows,
            "full_matrix_info": full_info,
            "full_matrix_payload_bytes": full_payload,
            "active_rows": active_rows,
            "active_matrix_info": active_info,
            "active_matrix_payload_bytes": active_payload,
        }

        def allocation_gate(label: str, facts: Mapping[str, Any]) -> None:
            if label == "V_GG":
                inventory_label = "q2_V_GG"
                allocation = int(facts["matrix_payload_bytes"])
                runtime.check_projected(inventory_label, allocation)
                runtime.reserve_inventory(
                    inventory_label,
                    {"matrix_payload_upper_bytes": allocation},
                    check_rss=False,
                )
                reserved_labels.add(inventory_label)
                return
            if label.startswith("internal_coupling_"):
                block = int(facts["block_index"])
                coupling = int(facts["coupling_bytes"])
                index_bytes = int(facts["index_bytes"])
                workspace = int(facts["workspace_bytes"])
                runtime.check_inventory_projected(
                    f"internal_{block}", coupling + index_bytes + workspace
                )
                runtime.check_projected(
                    f"internal_coupling_{block}",
                    coupling + index_bytes,
                    workspace_bytes=workspace,
                )
                return
            if label in {"S_V", "interface_matrix"}:
                inventory_label = (
                    "q2_S_V" if label == "S_V" else "q2_interface_matrix"
                )
                workspace_label = (
                    "q2_S_V_assembly_workspace"
                    if label == "S_V"
                    else "q2_interface_assembly_workspace"
                )
                allocation = int(facts["matrix_payload_bytes"])
                workspace = int(facts.get("workspace_bytes", 0))
                runtime.check_projected(
                    inventory_label, allocation, workspace_bytes=workspace
                )
                runtime.reserve_inventory(
                    inventory_label,
                    {"matrix_payload_upper_bytes": allocation},
                    check_rss=False,
                )
                reserved_labels.add(inventory_label)
                if workspace:
                    runtime.reserve_workspace(workspace_label, workspace)
                    reserved_workspaces.add(workspace_label)
                return
            raise ValueError(f"unexpected V14 Schur allocation gate: {label}")

        before, after = _factor_gates(runtime, local_limit=True)
        core = build_physical_interface_schur(
            active_volume,
            partition,
            carrier,
            port_data=port_data,
            resource_sample=lambda: runtime.sample("q2_internal_factor"),
            marker=runtime.marker,
            pre_numeric_gate=before,
            post_numeric_gate=after,
            allocation_gate=allocation_gate,
            owns_volume=True,
        )
        active_volume = None
        for workspace_label in tuple(reserved_workspaces):
            runtime.release_workspace(workspace_label)
            reserved_workspaces.remove(workspace_label)
        runtime.replace_inventory(
            "q2_V_GG",
            {
                "matrix_payload_bytes": _sparse_payload_bytes(
                    core.V_GG.getInfo(), int(core.V_GG.getSize()[0])
                )
            },
        )
        runtime.replace_inventory(
            "q2_S_V",
            {
                "matrix_payload_bytes": _sparse_payload_bytes(
                    core.S_V.getInfo(), int(core.S_V.getSize()[0])
                )
            },
        )
        runtime.replace_inventory(
            "q2_interface_matrix",
            {
                "matrix_payload_bytes": _sparse_payload_bytes(
                    core.interface_matrix.getInfo(),
                    int(core.interface_matrix.getSize()[0]),
                )
            },
        )
        runtime.marker(
            "q2_local_core_complete",
            {
                "internal_factor_count": len(core.internal),
                "factor_inventory": core.factor_facts,
                "volume": volume_facts,
            },
        )

        # This is deliberately before action checks and before the global
        # interface factor.  The reusable state contains only the matrices
        # and local couplings needed by the conditional later route; the
        # global augmented matrix is rebuilt, not copied into this archive.
        state = _q2_reusable_state(runtime, core)
        action_checks = _core_action_checks(runtime, core, common, storage_template)
        if not action_checks["passed"]:
            raise RuntimeError(
                f"V14 explicit/matrix-free action gate failed: {action_checks}"
            )
        reference_elimination = _q2_reference_elimination_checks(
            runtime,
            core,
            common,
            rhs_records,
            storage_template,
        )
        if not reference_elimination["passed"]:
            raise RuntimeError(
                "V14 reviewed reference elimination identity did not pass"
            )
        _save_packet(
            runtime.directory,
            "q2_pre_global_factor",
            {
                "schema": "task039extra.v14.q2-pre-global-factor.v1",
                "source_sha": runtime.source_sha,
                "partition": partition.audit(),
                "reusable_state_index": state["index"],
                "action_checks": action_checks,
                "reference_elimination": reference_elimination,
                "factor_solve_counts": _factor_solve_counts(core),
                "global_interface_factor_built": False,
            },
            runtime=runtime,
        )
        runtime.sample("q2_pre_global_factor_checkpoint")

        global_before, global_after = _factor_gates(
            runtime, local_limit=False, matrix_already_reserved=True
        )
        interface_facts = factorize_interface_schur(
            core,
            resource_sample=lambda: runtime.sample("q2_interface_factor"),
            marker=runtime.marker,
            pre_numeric_gate=global_before,
            post_numeric_gate=global_after,
        )
        runtime.marker(
            "q2_global_interface_factor_complete",
            {
                "interface_factor": interface_facts,
                "factor_solve_counts": _factor_solve_counts(core),
            },
        )

        solution_arrays: list[np.ndarray] = []
        solve_records: list[dict[str, Any]] = []
        for reviewed in rhs_records:
            runtime.set_phase("solve")
            runtime.marker("q2_rhs_solve_started", {"stem": reviewed["stem"]})
            started = time.perf_counter()
            rhs = storage_template.copy()
            rhs.array[:] = reviewed["rhs"]
            solution = None
            try:
                counts_before = _factor_solve_counts(core)
                solution, core_facts = core.solve(rhs, return_facts=True)
                interface_solution = np.asarray(
                    core_facts.pop("interface_solution"), dtype=np.complex128
                ).copy()
                counts_after_core = _factor_solve_counts(core)
                residual_facts, native_A4, native_volume, augmented_top, port = (
                    _q2_residual_arrays(
                        common,
                        reviewed,
                        solution,
                        interface_solution,
                        partition.gamma_rows,
                    )
                )
                refinements: list[dict[str, Any]] = []
                for refinement_index in range(2):
                    if residual_facts["native_A4_relative"] <= 1.0e-10:
                        break
                    refine_started = time.perf_counter()
                    refine_before = _factor_solve_counts(core)
                    correction_rhs = rhs.copy()
                    correction = None
                    try:
                        correction_rhs.array[:] = augmented_top
                        reduced, correction_port = core.reduce(
                            correction_rhs, port_rhs=port
                        )
                        delta_interface = core._interface_solve(
                            np.concatenate((reduced, correction_port))
                        )
                        correction = core.recover(
                            correction_rhs,
                            delta_interface[: partition.gamma_rows],
                        )
                        solution.axpy(-1.0, correction)
                        interface_solution -= delta_interface
                    finally:
                        if correction is not None:
                            correction.destroy()
                        correction_rhs.destroy()
                    refine_after = _factor_solve_counts(core)
                    (
                        residual_facts,
                        native_A4,
                        native_volume,
                        augmented_top,
                        port,
                    ) = _q2_residual_arrays(
                        common,
                        reviewed,
                        solution,
                        interface_solution,
                        partition.gamma_rows,
                    )
                    refinements.append(
                        {
                            "index": refinement_index + 1,
                            "elapsed_seconds": time.perf_counter() - refine_started,
                            "trigger": "native_A4_residual_above_1e-10",
                            "factor_solve_counts_before": refine_before,
                            "factor_solve_counts_after": refine_after,
                            "factor_solve_call_delta": _factor_count_delta(
                                refine_before, refine_after
                            ),
                        }
                    )
                interface_evidence = _q2_interface_residual(
                    core, rhs, interface_solution
                )
                counts_after_evidence = _factor_solve_counts(core)
                solution_array = np.asarray(solution.array).copy()
                solution_arrays.append(solution_array)
                solve_record = {
                    "stem": reviewed["stem"],
                    "logical_rhs": reviewed["logical_rhs"],
                    "elapsed_seconds": time.perf_counter() - started,
                    "core_facts": core_facts,
                    "augmented_residual": residual_facts,
                    "native_A4_relative_residual": residual_facts[
                        "native_A4_relative"
                    ],
                    "native_volume_top_relative_residual": residual_facts[
                        "native_volume_top_relative"
                    ],
                    "augmented_top_relative_residual": residual_facts[
                        "augmented_top_relative"
                    ],
                    "augmented_total_relative_residual": residual_facts[
                        "augmented_total_relative"
                    ],
                    "interface_relative_residual": interface_evidence[
                        "interface_relative_residual"
                    ],
                    "interface_reduced_rhs_relative_residual": interface_evidence[
                        "interface_reduced_rhs_relative_residual"
                    ],
                    "interface_residual_norm": float(
                        np.linalg.norm(interface_evidence["interface_residual"])
                    ),
                    "factor_solve_counts_before": counts_before,
                    "factor_solve_counts_after_core_solve": counts_after_core,
                    "factor_solve_counts_after_rhs_evidence": counts_after_evidence,
                    "factor_solve_call_delta_core_solve": _factor_count_delta(
                        counts_before, counts_after_core
                    ),
                    "factor_solve_call_delta_rhs_evidence": _factor_count_delta(
                        counts_before, counts_after_evidence
                    ),
                    "refinements": refinements,
                    "solution_sha256": _sha256_bytes(solution_array.tobytes()),
                    "reference_true_residual": reviewed["reference_true_residual"],
                }
                packet = _save_packet(
                    runtime.directory / "q2_rhs_packets",
                    reviewed["stem"],
                    {
                        "schema": "task039extra.v14.q2-rhs-packet.v2",
                        "identity": {
                            key: value
                            for key, value in reviewed.items()
                            if key
                            not in {
                                "rhs",
                                "reference_solution",
                                "reference_A4y",
                                "reference_map",
                            }
                        },
                        "solve": solve_record,
                        "x_storage": solution_array,
                        "interface_solution": interface_solution,
                        "native_A4_residual": native_A4,
                        "native_volume_top_residual": native_volume,
                        "augmented_top_residual": augmented_top,
                        "port_residual": port,
                        "interface_rhs": interface_evidence["interface_rhs"],
                        "interface_residual": interface_evidence[
                            "interface_residual"
                        ],
                    },
                    runtime=runtime,
                )
                solve_record["packet"] = packet
                solve_records.append(solve_record)
                if last_rhs is not None:
                    last_rhs.destroy()
                last_rhs = rhs.copy()
                last_gamma = interface_solution[: partition.gamma_rows].copy()
            except BaseException as exc:
                _save_packet(
                    runtime.directory / "q2_rhs_packets",
                    reviewed["stem"] + "_failure",
                    {
                        "schema": "task039extra.v14.q2-rhs-failure-packet.v1",
                        "identity": {
                            key: value
                            for key, value in reviewed.items()
                            if key
                            not in {
                                "rhs",
                                "reference_solution",
                                "reference_A4y",
                                "reference_map",
                            }
                        },
                        "error": {"type": type(exc).__name__, "message": str(exc)},
                        "factor_solve_counts": _factor_solve_counts(core),
                    },
                    runtime=runtime,
                )
                raise
            finally:
                if solution is not None:
                    solution.destroy()
                rhs.destroy()
            runtime.sample(f"q2_rhs_{reviewed['stem']}_complete")

        field = _field_metrics(
            runtime,
            common,
            solution_arrays,
            [record["reference_solution"] for record in rhs_records],
        )
        for solve, field_record in zip(solve_records, field, strict=True):
            solve["field_metrics"] = field_record
        max_native_A4 = max(
            item["native_A4_relative_residual"] for item in solve_records
        )
        max_augmented = max(
            item["augmented_total_relative_residual"] for item in solve_records
        )
        max_interface = max(
            item["interface_relative_residual"] for item in solve_records
        )
        max_field = max(
            max(
                item["field_metrics"]["field_l2_relative"],
                item["field_metrics"]["scaled_curl_relative"],
            )
            for item in solve_records
        )
        if last_rhs is None or last_gamma is None:
            raise RuntimeError("Q2 did not retain a final RHS/recovery state")
        pre_release_solution = solution_arrays[-1].copy()
        core.release_explicit_schur()
        runtime.release_inventory("interface")
        runtime.release_inventory("q2_interface_matrix")
        runtime.release_inventory("q2_S_V")
        runtime.release_inventory("q2_active_volume")
        released = core.recover(last_rhs, last_gamma)
        try:
            release_relative = float(
                np.linalg.norm(released.array - pre_release_solution)
            ) / max(float(np.linalg.norm(pre_release_solution)), np.finfo(float).tiny)
        finally:
            released.destroy()
        # As in Q1, the original native A4 residual is the numerical
        # admission line.  Augmented and interface residuals remain recorded
        # for construction/error diagnosis; the reduced-RHS-normalized
        # interface number cannot replace the original A4 criterion.
        residual_pass = max_native_A4 <= 1.0e-10
        field_pass = max_field <= 1.0e-8
        record = {
            "schema": "task039extra.v14.q2-schur-direct.v2",
            "status": "Q2_SCHUR_DIRECT_PASS"
            if residual_pass and field_pass and release_relative <= 1.0e-10
            else "EXACT_CONTROL_UNQUALIFIED",
            "official_result": bool(
                residual_pass and field_pass and release_relative <= 1.0e-10
            ),
            "rhs": [
                {
                    key: value
                    for key, value in item.items()
                    if key
                    not in {"rhs", "reference_solution", "reference_A4y", "reference_map"}
                }
                for item in rhs_records
            ],
            "partition": partition.audit(),
            "volume": volume_facts,
            "factor_inventory": core.factor_facts,
            "global_interface_factor": interface_facts,
            "reusable_state": state,
            "action_checks": action_checks,
            "solve_records": solve_records,
            "gates": {
                "native_A4_relative_residual": 1.0e-10,
                "field_l2_and_scaled_curl": 1.0e-8,
                "admission_basis": "original_A4_and_P64_field_metrics",
                "post_release_recovery": 1.0e-10,
                "max_native_A4_relative_residual": max_native_A4,
                "max_augmented_total_relative_residual": max_augmented,
                "max_interface_relative_residual": max_interface,
                "max_interface_reduced_rhs_relative_residual": max(
                    item["interface_reduced_rhs_relative_residual"]
                    for item in solve_records
                ),
                "augmented_and_interface_residuals_are_diagnostics_only": True,
                "max_field_l2_or_scaled_curl": max_field,
                "post_release_recovery_relative": release_relative,
            },
            "lifecycle": {
                "internal_factor_count": len(core.internal),
                "global_interface_factor_count": 1,
                "factor_live_through_all_rhs_and_metrics": True,
                "explicit_schur_released_before_final_recovery_check": True,
                "local_factors_retained_for_recovery": True,
                "factor_solve_counts_after_all_rhs": _factor_solve_counts(core),
                "inventory_peak_bytes": runtime.inventory_peak_bytes,
                "workspace_peak_bytes": runtime.workspace_peak_bytes,
            },
        }
        runtime.marker("q2_schur_direct_complete", record)
        return record
    finally:
        for workspace_label in tuple(reserved_workspaces):
            runtime.release_workspace(workspace_label)
        if last_rhs is not None:
            last_rhs.destroy()
        if core is not None:
            core.destroy()
        elif active_volume is not None:
            active_volume.destroy()
        if full_volume is not None:
            full_volume.destroy()
            runtime.release_inventory("q2_full_volume")
        if storage_template is not None:
            storage_template.destroy()
        for label in (
            "interface",
            "q2_interface_matrix",
            "q2_S_V",
            "q2_V_GG",
            "q2_active_volume",
            "q2_full_volume",
        ):
            runtime.release_inventory(label)
        for index in range(42):
            runtime.release_inventory(f"internal_{index}")


def _q3_action_checks(
    runtime: _V14Runtime,
    core: Any,
    common: Mapping[str, Any],
    storage_template: Any,
) -> dict[str, Any]:
    """Check the matrix-free physical Gamma action before releasing ``S_V``."""

    runtime.set_phase("action_checks")
    gamma = core.V_GG.createVecRight()
    gamma_y = gamma.duplicate()
    gamma_mf = gamma.duplicate()
    gamma_explicit = gamma.duplicate()
    gamma_adjoint = gamma.duplicate()
    gamma_adj_explicit = gamma.duplicate()
    zero_storage = storage_template.duplicate()
    physical = physical_adjoint = recovered = native_output = None
    try:
        gamma.array[:] = np.arange(gamma.getLocalSize(), dtype=np.float64) + 0.25j
        gamma.array[:] /= max(float(gamma.norm()), 1.0)
        gamma_y.array[:] = 1.0 + 1j * np.arange(
            gamma_y.getLocalSize(), dtype=np.float64
        )
        gamma_y.array[:] /= max(float(gamma_y.norm()), 1.0)
        core.S_V.mult(gamma, gamma_explicit)
        core.apply_volume_schur(gamma, gamma_mf)
        core.S_V.multHermitian(gamma, gamma_adj_explicit)
        core.apply_volume_schur_adjoint(gamma, gamma_adjoint)

        zero_storage.set(0)
        recovered = core.recover(zero_storage, gamma)
        native_output = recovered.duplicate()
        common["p4"]["physical_action"].apply(recovered, native_output)
        native_gamma = np.asarray(
            native_output.array[core.partition.gamma_full_indices],
            dtype=np.complex128,
        )
        physical = core.apply_physical_schur(gamma)
        physical_difference = float(
            np.linalg.norm(native_gamma - physical.array)
        ) / max(float(physical.norm()), np.finfo(float).tiny)

        physical_adjoint = core.apply_physical_schur_adjoint(gamma)
        expected_adjoint = gamma_adj_explicit.duplicate()
        try:
            expected_adjoint.array[:] = gamma_adj_explicit.array
            for entry in core.port_data:
                value = np.dot(
                    np.conj(entry["b_values"]), gamma.array[entry["b_gamma"]]
                ) / np.conj(entry["normalization_h"])
                expected_adjoint.array[entry["d_gamma"]] += (
                    np.conj(entry["d_values"]) * value
                )
            physical_adjoint_difference = float(
                np.linalg.norm(physical_adjoint.array - expected_adjoint.array)
            ) / max(float(expected_adjoint.norm()), np.finfo(float).tiny)
        finally:
            expected_adjoint.destroy()

        block_input = np.empty((gamma.getLocalSize(), 2), dtype=np.complex128)
        block_input[:, 0] = gamma.array
        block_input[:, 1] = gamma_y.array
        block_output = core.apply_physical_schur_block(block_input)
        block_first_difference = float(
            np.linalg.norm(block_output[:, 0] - physical.array)
        ) / max(float(physical.norm()), np.finfo(float).tiny)
        physical_y = core.apply_physical_schur(gamma_y)
        try:
            block_second_difference = float(
                np.linalg.norm(block_output[:, 1] - physical_y.array)
            ) / max(float(physical_y.norm()), np.finfo(float).tiny)
        finally:
            physical_y.destroy()

        adjoint_y = core.apply_physical_schur_adjoint(gamma_y)
        try:
            lhs = complex(physical.dot(gamma_y))
            rhs_inner = complex(gamma.dot(adjoint_y))
            inner_scale = max(
                abs(lhs),
                abs(rhs_inner),
                float(physical.norm()) * float(gamma_y.norm()),
                np.finfo(float).tiny,
            )
            adjoint_inner_relative = abs(lhs - rhs_inner) / inner_scale
        finally:
            adjoint_y.destroy()

        facts = {
            "schema": "task039extra.v14.q3-action-checks.v1",
            "volume_explicit_vs_matrix_free": _vec_relative(
                gamma_explicit, gamma_mf
            ),
            "volume_adjoint_explicit_vs_matrix_free": _vec_relative(
                gamma_adj_explicit, gamma_adjoint
            ),
            "physical_schur_vs_native_carrier": physical_difference,
            "physical_schur_adjoint_formula": physical_adjoint_difference,
            "physical_block_first_column": block_first_difference,
            "physical_block_second_column": block_second_difference,
            "physical_schur_complex_inner_product_relative": float(
                adjoint_inner_relative
            ),
            "global_dense_schur_constructed": False,
            "interface_matrix_built": False,
            "matrix_free_block_action": True,
            "batch_columns": 32,
        }
        facts["limits"] = {
            "action_bridge": 1.0e-10,
            "physical_schur": 1.0e-10,
            "adjoint_inner_product": 1.0e-10,
        }
        facts["passed"] = bool(
            facts["volume_explicit_vs_matrix_free"] <= facts["limits"]["action_bridge"]
            and facts["volume_adjoint_explicit_vs_matrix_free"]
            <= facts["limits"]["action_bridge"]
            and facts["physical_schur_vs_native_carrier"]
            <= facts["limits"]["physical_schur"]
            and facts["physical_schur_adjoint_formula"]
            <= facts["limits"]["physical_schur"]
            and facts["physical_block_first_column"]
            <= facts["limits"]["physical_schur"]
            and facts["physical_block_second_column"]
            <= facts["limits"]["physical_schur"]
            and facts["physical_schur_complex_inner_product_relative"]
            <= facts["limits"]["adjoint_inner_product"]
        )
        runtime.marker("v14_q3_action_checks_complete", facts)
        runtime.sample("q3_action_checks_complete")
        return facts
    finally:
        for value in (
            gamma,
            gamma_y,
            gamma_mf,
            gamma_explicit,
            gamma_adjoint,
            gamma_adj_explicit,
            zero_storage,
            physical,
            physical_adjoint,
            recovered,
            native_output,
        ):
            if value is not None:
                value.destroy()


def _q3_representative_patches(
    patch_rows: tuple[np.ndarray, ...],
    port_data: list[Mapping[str, Any]],
) -> tuple[int, int, dict[str, Any]]:
    """Choose the two deterministic geometry/graph representative patches."""

    sizes = [int(rows.size) for rows in patch_rows]
    # Form the physical nonzero DtN support once.  Rebuilding a row set for
    # every port and every patch made representative selection needlessly
    # quadratic in Python and, more importantly, admitted zero carrier
    # entries as if they were physical support.
    nonzero_dtn_support: set[int] = set()
    for entry in port_data:
        for rows, values in (
            (entry["b_gamma"], entry["b_values"]),
            (entry["d_gamma"], entry["d_values"]),
        ):
            row_array = np.asarray(rows, dtype=np.int64).reshape(-1)
            value_array = np.asarray(values, dtype=np.complex128).reshape(-1)
            if row_array.size != value_array.size:
                raise ValueError("DtN representative support/value sizes differ")
            nonzero_dtn_support.update(
                int(row)
                for row, value in zip(row_array, value_array, strict=True)
                if abs(value) > 0.0
            )
    patch_sets = [set(np.asarray(rows, dtype=np.int64).tolist()) for rows in patch_rows]
    support_sets = [patch_set & nonzero_dtn_support for patch_set in patch_sets]
    support_counts = [len(values) for values in support_sets]
    largest = min(range(len(patch_rows)), key=lambda index: (-sizes[index], index))
    dtn_order = sorted(
        range(len(patch_rows)),
        key=lambda index: (-support_counts[index], -sizes[index], index),
    )
    dtn_patch = next((index for index in dtn_order if index != largest), None)
    if dtn_patch is None:
        raise ValueError("Q3 representative patch selection needs two distinct patches")
    facts = {
        "selection_rule": (
            "largest canonical seed/Gamma support; then largest nonzero DtN "
            "support, tie-broken by size and patch id, forced distinct"
        ),
        "largest_patch": largest,
        "dtn_patch": dtn_patch,
        "patch_sizes": sizes,
        "nonzero_dtn_support_counts": support_counts,
        "nonzero_dtn_support_union_count": len(nonzero_dtn_support),
        "largest_patch_rows_sha256": _sha256_bytes(
            np.ascontiguousarray(patch_rows[largest]).tobytes()
        ),
        "dtn_patch_rows_sha256": _sha256_bytes(
            np.ascontiguousarray(patch_rows[dtn_patch]).tobytes()
        ),
    }
    return largest, dtn_patch, facts


def _q3_delta_from_unweighted_p4_mass(
    runtime: _V14Runtime,
    common: Mapping[str, Any],
    partition: Any,
    resolved_payload: Mapping[str, Any],
) -> tuple[np.ndarray, dict[str, Any]]:
    """Reuse the qualified V13 p0 diagonal after current identity checks.

    The diagonal was already proved equivalent to the unweighted p4 mass in
    V13.  Q3 only loads that hash-bound packet and restricts it to the current
    Gamma map; it never reconstructs a second metric or cell-basis library.
    """

    from src.runners.physical_diagnostic_completion import load_packet
    from src.runners.physical_macro_controls import _mapping_identity_sha256
    from src.solvers.condensed_fine_reference import native_map_arrays
    from src.solvers.physical_macro_dd4 import _identity_hash_arrays

    runtime.set_phase("assembly")
    runtime.marker(
        "q3_unweighted_p4_mass_diagonal_started",
        {
            "definition": "V13 qualified integral conjugate(E) dot E; no material weight",
            "construction": "hash-bound p0 packet reuse; no metric rebuild",
        },
    )
    root = _repo_root()
    compact_path = root / "docs/task039_extra_physical_multilevel/outcomes/records/p4_direction_diagnosis_v13.json"
    p0_path = root / (
        "benchmarks/artifacts/task39extra/p4_direction_diagnosis_v13/"
        "e46fec48dc073a745e9b7e6c9186a147aefbc0a0/diagnosis/records/"
        "p0_metric_equivalence.json"
    )
    expected_physical = "9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f"
    qualified_notch_physical = "7a4d2a797a274fd4a02955647e91288908dd6a457c37984535fa2db9bfec06ec"
    expected_mode = "dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2"
    expected_p0_json_sha = "c05ff1a34a387e9a2a8a14f492349a4874e3ba160ed254ae11b8533243cfa3e9"
    expected_p0_npz_sha = "c0fc7ad54001f11033cea4c0340075da6569df828f2bd94430835580677a1e83"
    expected_map_summary_sha = "f175bfce77ca4a6811f12e800c213ade75afd0ce866ae57ae9f5449130cca0fe"
    expected_local_map_sha = "f788b961933cf814014feacea4a787ded7b8041bd51111a30424c042e4721cbd"

    compact = json.loads(compact_path.read_text(encoding="utf-8"))
    if (
        compact.get("source_sha") != "e46fec48dc073a745e9b7e6c9186a147aefbc0a0"
        or compact.get("physical_model_sha256") != expected_physical
        or compact.get("ordered_mode_sha256") != expected_mode
        or compact.get("p0", {}).get("record_sha256") != expected_p0_json_sha
    ):
        raise ValueError("V13 p0 compact identity is not the qualified physical packet")
    if _sha256_file(p0_path) != expected_p0_json_sha:
        raise ValueError("V13 p0 JSON packet hash changed")
    p0_record = json.loads(p0_path.read_text(encoding="utf-8"))
    array_meta = p0_record.get("arrays")
    if not isinstance(array_meta, Mapping):
        raise ValueError("V13 p0 packet has no hash-bound array archive")
    array_path = Path(array_meta["path"])
    if not array_path.is_file() or _sha256_file(array_path) != expected_p0_npz_sha:
        raise ValueError("V13 p0 fixed-diagonal archive hash changed")
    if array_meta.get("sha256") != expected_p0_npz_sha:
        raise ValueError("V13 p0 packet does not name the qualified array archive")

    actual_physical = resolved_payload.get("provenance", {}).get(
        "physical_model_sha256"
    )
    actual_mode = str(common["p4"]["mode_sha256"])
    qualified_physical = {expected_physical, qualified_notch_physical}
    if actual_physical not in qualified_physical or actual_mode != expected_mode:
        raise ValueError(
            "current physical or ordered-mode identity is not one of the "
            "qualified V13 unweighted-diagonal reuse identities"
        )
    current_map = native_map_arrays(
        common["levels"]["spaces"][4], common["levels"]["floquets"][4]
    )
    current_map_summary_sha = _mapping_identity_sha256(current_map)
    current_local_map_sha = _identity_hash_arrays(
        {
            key: current_map[key]
            for key in (
                "dofmap",
                "slaves",
                "masters",
                "coefficients",
                "offsets",
                "independent_indices",
            )
        }
    )
    if current_map_summary_sha != expected_map_summary_sha:
        raise ValueError("current native p4 map summary differs from V13 p0")
    if current_local_map_sha != expected_local_map_sha:
        raise ValueError("current local p4 map identity differs from V13 p0")
    p0 = load_packet(p0_path)
    active_delta = np.ascontiguousarray(
        np.asarray(p0.get("fixed_diagonal_values"), dtype=np.float64)
    )
    if _sha256_bytes(active_delta.tobytes()) != p0_record["fixed_diagonal"]["sha256"]:
        raise ValueError("V13 p0 fixed diagonal content hash differs")
    if active_delta.shape != (partition.active_rows,):
        raise ValueError("V13 p0 Delta has an unexpected active-row shape")
    delta_gamma = np.ascontiguousarray(
        active_delta[partition.gamma_active_indices], dtype=np.float64
    )
    if (
        delta_gamma.shape != (partition.gamma_rows,)
        or not np.all(np.isfinite(delta_gamma))
        or np.any(delta_gamma <= 0.0)
    ):
        raise ValueError("unweighted p4 Delta is not finite and strictly positive")
    facts = {
        "definition": "V13 qualified unweighted p4 lossless mass diagonal restricted to Gamma",
        "material_weight_included": False,
        "reuse": True,
        "metric_rebuilt": False,
        "p0_json": str(p0_path),
        "p0_json_sha256": expected_p0_json_sha,
        "p0_npz": str(array_path),
        "p0_npz_sha256": expected_p0_npz_sha,
        "source_physical_model_sha256": expected_physical,
        "current_physical_model_sha256": actual_physical,
        "qualified_physical_identities": sorted(qualified_physical),
        "reuse_basis": "same geometry/map/mode; unweighted material-independent diagonal",
        "source_ordered_mode_sha256": expected_mode,
        "current_ordered_mode_sha256": actual_mode,
        "physical_model_sha256": actual_physical,
        "ordered_mode_sha256": actual_mode,
        "constraint_map_sha256": current_map_summary_sha,
        "constraint_map_identity": current_local_map_sha,
        "active_rows": int(active_delta.size),
        "gamma_rows": int(delta_gamma.size),
        "active_sha256": _sha256_bytes(active_delta.tobytes()),
        "gamma_sha256": _sha256_bytes(delta_gamma.tobytes()),
        "minimum": float(np.min(delta_gamma)),
        "maximum": float(np.max(delta_gamma)),
    }
    runtime.marker("q3_unweighted_p4_mass_diagonal_complete", facts)
    return delta_gamma, facts


def _q3_array_summary(value: Any) -> dict[str, Any]:
    array = np.ascontiguousarray(np.asarray(value))
    return {
        "shape": list(array.shape),
        "dtype": str(array.dtype),
        "norm": float(np.linalg.norm(array)),
        "sha256": _sha256_bytes(array.tobytes()),
    }


def _q3_interface_operation_audit(
    interface_facts: Mapping[str, Any],
    internal_factor_count: int,
) -> dict[str, Any]:
    """Recompute the finite work envelope from the actual phase counters.

    Four internal solves per block and 84 local backsolves are maxima.
    A disconnected block may skip a reduction/Schur solve; the complete
    reduce/J-C-J/recover route must still be present.
    """

    count = int(internal_factor_count)
    if count < 0:
        raise ValueError("internal_factor_count must be non-negative")
    internal = interface_facts.get("factor_solve_delta", ())
    local = interface_facts.get("local_patch_solve_delta", ())
    operations = interface_facts.get("operation_counts") or {}
    phases = operations.get("factor_solve_delta_by_phase") or {}

    def valid_counts(values, size, limit):
        return (isinstance(values, (list, tuple, np.ndarray))
                and len(values) == size
                and all(isinstance(v, (int, np.integer)) and 0 <= v <= limit
                        for v in values))

    internal_valid = valid_counts(internal, count, 4)
    local_valid = (isinstance(local, (list, tuple, np.ndarray))
                   and 0 < len(local) <= 42
                   and valid_counts(local, len(local), 2))
    phase_names = ("reduce", "S1", "S2", "recover")
    phase_valid = all(valid_counts(phases.get(name, ()), count, 1)
                      for name in phase_names)
    phase_matches = bool(internal_valid and phase_valid and all(
        sum(phases[name][i] for name in phase_names) == internal[i]
        for i in range(count)))
    route_complete = bool(
        operations.get("route") == ["reduce", "J1", "S1", "E1", "S2", "J2", "recover"]
        and operations.get("schur_action_count") == 2
        and operations.get("local_action_count") == 2
        and interface_facts.get("local_smoother_apply_count") == 2
        and interface_facts.get("coarse_solve_count") == 1
        and phase_valid and all(v == 1 for v in phases["recover"])
        and interface_facts.get("ksp_created") is False
        and interface_facts.get("inner_iteration_count") == 0
        and interface_facts.get("reference_used") is False)
    within_limits = bool(
        internal_valid and local_valid
        and interface_facts.get("local_patch_apply_count") == sum(local))
    total = int(sum(internal)) if internal_valid else None
    return {
        "schema": "task039extra.v14.interface-operation-audit.v1",
        "internal_factor_count": count,
        "factor_solve_delta": list(internal) if internal_valid else None,
        "internal_factor_solve_total": total,
        "internal_factor_solve_max_per_block": int(max(internal, default=0)) if internal_valid else None,
        "internal_factor_solve_limit_total": 4 * count,
        "internal_factor_solve_limit_per_block": 4,
        "local_patch_apply_count": int(sum(local)) if local_valid else None,
        "local_patch_apply_limit": 84,
        "local_smoother_apply_count": interface_facts.get("local_smoother_apply_count"),
        "coarse_solve_count": interface_facts.get("coarse_solve_count"),
        "coarse_solve_limit": 1,
        "within_upper_bounds": within_limits,
        "phase_sum_matches_per_block": phase_matches,
        "route_basis": "actual_adapter_phase_counters",
        "complete_route": route_complete,
        "passed": bool(route_complete and phase_matches and within_limits),
    }


def _q3_local_setup_prediction(
    patch_rows: tuple[np.ndarray, ...],
    process_order: tuple[int, ...],
    representative_patch_ids: tuple[int, int],
    representative_durations: Mapping[int, float],
) -> dict[str, Any]:
    """Predict the remaining sequential local setup from measured patches.

    The first two patches are the frozen geometry/graph representatives.  The
    remaining work is estimated from the largest measured seconds-per-
    ``(rows**2 + rows)`` unit.  This empirical extrapolation includes extraction,
    LU and SVD in the measured samples, but is not a proven runtime upper bound:
    conditioning, fill and system load can change their relative costs.  The
    measured workflow clock remains authoritative.
    """

    rows_tuple = tuple(np.asarray(rows, dtype=np.int64).reshape(-1) for rows in patch_rows)
    order = tuple(int(patch_id) for patch_id in process_order)
    representatives = tuple(int(patch_id) for patch_id in representative_patch_ids)
    if len(representatives) != 2 or representatives[0] == representatives[1]:
        raise ValueError("Q3 setup prediction needs two distinct representatives")
    if sorted(order) != list(range(len(rows_tuple))):
        raise ValueError("Q3 setup prediction process order is not a permutation")
    if any(
        patch_id < 0 or patch_id >= len(rows_tuple)
        for patch_id in representatives
    ):
        raise ValueError("Q3 setup prediction representative is outside patch rows")
    if any(patch_id not in order[:2] for patch_id in representatives):
        raise ValueError("Q3 representatives must be processed before remaining patches")

    structural_weight = {
        patch_id: int(rows_tuple[patch_id].size * (rows_tuple[patch_id].size + 1))
        for patch_id in range(len(rows_tuple))
    }
    durations: dict[int, float] = {}
    for patch_id in representatives:
        duration = float(representative_durations.get(patch_id, -1.0))
        if not np.isfinite(duration) or duration < 0.0:
            raise ValueError("Q3 representative duration must be finite and non-negative")
        durations[patch_id] = duration
    rates = [
        durations[patch_id] / max(structural_weight[patch_id], 1)
        for patch_id in representatives
    ]
    seconds_per_structure_unit = max(rates, default=0.0)
    remaining_patch_ids = tuple(
        patch_id for patch_id in order if patch_id not in set(representatives)
    )
    representative_structure_weight = int(
        sum(structural_weight[patch_id] for patch_id in representatives)
    )
    remaining_structure_weight = int(
        sum(structural_weight[patch_id] for patch_id in remaining_patch_ids)
    )
    measured_representative_seconds = float(sum(durations.values()))
    predicted_remaining_seconds = float(
        seconds_per_structure_unit * remaining_structure_weight
    )
    return {
        "schema": "task039extra.v14.q3-local-setup-prediction.v1",
        "classification": "derived_empirical_estimate_not_measured",
        "proven_runtime_upper_bound": False,
        "representative_patch_ids": list(representatives),
        "representative_durations_seconds": {
            str(patch_id): durations[patch_id] for patch_id in representatives
        },
        "representative_structure_weight": representative_structure_weight,
        "remaining_patch_ids": list(remaining_patch_ids),
        "remaining_structure_weight": remaining_structure_weight,
        "patch_structure_weights": {
            str(patch_id): structural_weight[patch_id]
            for patch_id in order
        },
        "seconds_per_structure_unit_upper": seconds_per_structure_unit,
        "measured_representative_seconds": measured_representative_seconds,
        "predicted_remaining_seconds": predicted_remaining_seconds,
        "predicted_local_setup_seconds": (
            measured_representative_seconds + predicted_remaining_seconds
        ),
        "prediction_formula": (
            "sum(measured representative seconds) + max(measured seconds/"
            "(rows^2+rows)) * remaining structure weight"
        ),
    }


@contextmanager
def _v14_balanced_adapter(
    runtime,
    common,
    fint,
    *,
    capture_vectors=False,
    repair_policy=None,
    repair_vector_sink=None,
    repair_vector_capture=None,
    logical_apply_hook=None,
    pc_fine_action_factory=None,
    packed_power10=False,
    sum_factorized_work=False,
    sum_factorized_power10=None,
    direct_selected_backend=False,
    reuse_projection_work=False,
):
    """Own H6 and its audit buffers; borrow the existing fixed interface stack."""

    from src.solvers.fullspace_physical_intermediate import apply_owned
    from src.solvers.fullspace_physical_intermediate_runtime import AlgebraicOwnerTransfer
    from src.solvers.physical_interface_balanced import InterfaceBalancedCoupling
    from src.solvers.physical_light_setup import build_light_h6_setup
    from petsc4py import PETSc

    h6_setup = _v14_balanced_h6_setup_facts(common)
    n6 = int(h6_setup["n6"])
    n4 = int(h6_setup["n4"])
    # Same-degree positive setup uses the already-qualified H6 constructor.
    # The two existing physical component payloads and twelve fine vectors
    # provide a construction estimate; measured RSS remains independent.
    setup_estimate = int(h6_setup["setup_estimate_bytes"])
    runtime.check_inventory_projected("v14_h6_setup", setup_estimate)
    runtime.check_projected("v14_h6_setup", setup_estimate, workspace_bytes=64 << 20)
    runtime.marker("v14_h6_setup_preallocation", {
        "classification": "derived_conservative_estimate",
        "inventory_estimate_bytes": setup_estimate,
        "temporary_allowance_bytes": 64 << 20,
        "basis": "two same-degree physical component payloads plus twelve fine vectors",
    })
    positive = pc = None
    pc_fine_action = common["fine"]["physical_action"]
    pc_fine_action_bundle = None
    candidate_facts = {}
    pc_fine_inventory_live = False
    live_workspaces = set()
    inventory_live = False
    cleaned = False

    def cleanup_balanced_objects() -> None:
        nonlocal cleaned, pc, positive, pc_fine_action_bundle
        nonlocal pc_fine_inventory_live
        if cleaned:
            return
        cleaned = True
        if pc is not None:
            pc.destroy()
            pc = None
        if pc_fine_action_bundle is not None:
            pc_fine_action_bundle["physical_action"].destroy()
            pc_fine_action_bundle.clear()
            pc_fine_action_bundle = None
        if positive is not None:
            h6 = positive.pop("h6", None)
            shell = positive.pop("p6_shell", None)
            if h6 is not None:
                h6.destroy()
            if shell is not None:
                shell.destroy()
            positive.clear()
            positive = None
        for label in live_workspaces:
            runtime.release_workspace(label)
        live_workspaces.clear()
        if pc_fine_inventory_live:
            runtime.release_inventory("v24_pc_a6_candidate")
        if inventory_live:
            runtime.release_inventory("v14_h6")
        runtime._deferred_balanced_cleanup = None
        runtime._defer_balanced_release = False
    try:
        runtime.reserve_workspace("v14_h6_build", 64 << 20)
        live_workspaces.add("v14_h6_build")
        positive = build_light_h6_setup(
            common["levels"],
            common["cfg"],
            runtime.marker,
            packed_power10=packed_power10,
            sum_factorized_work=sum_factorized_work,
            sum_factorized_power10=sum_factorized_power10,
            direct_selected_backend=direct_selected_backend,
            reuse_projection_work=reuse_projection_work,
            batched_target_grouping=direct_selected_backend,
        )
        h6, shell = positive["h6"], positive["p6_shell"]
        transfer = AlgebraicOwnerTransfer(common["transfer"])
        components = dict(shell.action.audit["retained_numeric_payload_components"])
        components["h6_diagonal_bytes"] = int(shell.diagonal.array.nbytes)
        for name in ("_inv_sqrt", "_scaled_input", "_scaled_action", "_rhs_scaled",
                     "_residual", "_direction", "_solution", "_action"):
            components["h6" + name + "_bytes"] = int(getattr(h6, name).array.nbytes)
        components["algebraic_transfer_slave_indices_bytes"] = int(
            transfer.fine_slaves.nbytes + transfer.coarse_slaves.nbytes)
        runtime.reserve_inventory("v14_h6", components, check_rss=False)
        inventory_live = True
        runtime.release_workspace("v14_h6_build")
        live_workspaces.remove("v14_h6_build")
        if pc_fine_action_factory is not None:
            if direct_selected_backend:
                pc_fine_action_bundle = pc_fine_action_factory(
                    common,
                    geometry_bundle=positive.get("geometry_bundle"),
                )
            else:
                pc_fine_action_bundle = pc_fine_action_factory(common)
            if not isinstance(pc_fine_action_bundle, dict):
                raise TypeError("PC fine action factory must return an action bundle")
            pc_fine_action = pc_fine_action_bundle["physical_action"]
            candidate_facts = pc_fine_action_bundle["facts"]
            if not isinstance(candidate_facts, dict):
                raise TypeError("PC fine action facts must be a mapping")
            candidate_components = {
                "material_function_array_bytes": int(
                    candidate_facts["material_function_array_bytes"]
                )
            }
            for index, audit in enumerate(candidate_facts["component_audits"]):
                if not isinstance(audit, dict):
                    raise TypeError("PC fine component audit must be a mapping")
                components = audit["retained_numeric_payload_components"]
                if not isinstance(components, Mapping):
                    raise ValueError("PC fine component payload audit is missing")
                for name, amount in components.items():
                    candidate_components[f"component_{index}_{name}"] = int(amount)
            runtime.reserve_inventory(
                "v24_pc_a6_candidate", candidate_components, check_rss=False
            )
            pc_fine_inventory_live = True
            candidate_kernel_temporary_bytes = max(
                int(kernel["temporary_budget_bytes"])
                for kernel in candidate_facts["kernels"]
            )
            runtime.marker(
                "v24_pc_a6_candidate_ready",
                {
                    "candidate": candidate_facts,
                    "inventory_components": candidate_components,
                    "native_a6_authority": "common.fine.physical_action",
                    "dtn_ownership": "borrowed_common_fine_dtn_action",
                },
            )
        else:
            candidate_kernel_temporary_bytes = 0
        # Fine work vectors, retained audit copies, p4 residual copies and
        # H6's bounded packed-kernel temporaries share the existing 1 GiB pool.
        fine_vectors = 64 if capture_vectors else 40
        coarse_vectors = 16 if capture_vectors else 12
        h6_kernel_temporary_bytes = int(
            positive["light_facts"]["kernel"]["temporary_budget_bytes"]
        )
        kernel_temp = max(h6_kernel_temporary_bytes, candidate_kernel_temporary_bytes)
        pc_workspace = _v14_balanced_apply_workspace_bytes(
            n6,
            n4,
            kernel_temp,
            fine_vector_count=fine_vectors,
            coarse_vector_count=coarse_vectors,
        )
        prefix_workspace_facts = None
        runtime.reserve_workspace("v14_balanced_apply", pc_workspace)
        live_workspaces.add("v14_balanced_apply")
        if logical_apply_hook is not None:
            condensed = fint.inverse.condensed
            if condensed is None:
                raise RuntimeError(
                    "V24 prefix workspace requires the live condensed p4 system"
                )
            prefix_workspace_facts = _v24_p4_prefix_workspace_facts(
                n4,
                int(condensed.trace_rows),
                int(condensed.appended_rows),
                scalar_bytes=np.dtype(PETSc.ScalarType).itemsize,
                index_bytes=np.dtype(PETSc.IntType).itemsize,
            )
            runtime.reserve_workspace(
                "v24_p4_prefix_diagnostic",
                prefix_workspace_facts["workspace_upper_bytes"],
            )
            live_workspaces.add("v24_p4_prefix_diagnostic")
        runtime.marker("v14_balanced_workspace", {
            "fine_vector_upper_count": fine_vectors,
            "coarse_vector_upper_count": coarse_vectors,
            "h6_kernel_temporary_bytes": h6_kernel_temporary_bytes,
            "pc_a6_kernel_temporary_bytes": candidate_kernel_temporary_bytes,
            "kernel_temporary_bytes": kernel_temp,
            "ordinary_balanced_workspace_bytes": pc_workspace,
            "v24_prefix_workspace": prefix_workspace_facts,
            "workspace_upper_bytes": int(
                pc_workspace
                + (
                    prefix_workspace_facts["workspace_upper_bytes"]
                    if prefix_workspace_facts is not None
                    else 0
                )
            ),
            "scope": "new PC/ledger/capture vectors; outer Krylov storage accounted separately",
        })
        candidate_a6_callback = lambda x: apply_owned(pc_fine_action, x)
        native_a6_callback = lambda x: apply_owned(
            common["fine"]["physical_action"], x
        )
        candidate_h6_callback = h6.apply
        pc = InterfaceBalancedCoupling(
            candidate_a6_callback,
            lambda x: apply_owned(common["p4"]["physical_action"], x),
            transfer, fint, h6.apply,
            save=lambda name, facts: _save_packet(
                runtime.directory / "inexact_balance", name, facts, runtime=runtime),
            checkpoint=lambda: runtime.sample("v14_balanced_checkpoint"),
            capture_vectors=capture_vectors,
            repair_policy=repair_policy,
            repair_vector_sink=repair_vector_sink,
            repair_vector_capture=repair_vector_capture,
            logical_apply_hook=logical_apply_hook,
        )
        # Keep the callbacks used by the BAL_H closure explicit.  The public
        # ``_pc_fine_action`` attribute is provenance only and does not alter
        # the lambda already captured by ``InterfaceBalancedCoupling``.
        pc._candidate_a6_callback = candidate_a6_callback
        pc._native_a6_callback = native_a6_callback
        pc._candidate_h6_callback = candidate_h6_callback
        pc._pc_fine_action = pc_fine_action
        pc._pc_fine_action_facts = dict(candidate_facts)
        pc._pc_fine_action_role = (
            "candidate_pc_internal_a6"
            if pc_fine_action_bundle is not None
            else "native_a6_witness"
        )
        runtime.sample("v14_balanced_adapter_ready")
        yield pc, positive
    finally:
        if getattr(runtime, "_defer_balanced_release", False):
            runtime._deferred_balanced_cleanup = cleanup_balanced_objects
        else:
            cleanup_balanced_objects()


def _q3_balanced_p6_audit(runtime, common, fint):
    """Check the actual c1/H6-generated feedback and eps1-eps2 closure."""

    from src.runners.physical_recursive_controls import load_recursive_balanced_inputs
    from src.solvers.condensed_fine_reference import native_map_arrays
    from src.solvers.fullspace_physical_intermediate import apply_owned
    from src.solvers.physical_map_identity import compare_native_map_identity

    runtime.reserve_workspace("q3_balanced_inputs", 32 << 20)
    e = q = ae = z = az = None
    pc = None
    try:
        inputs = load_recursive_balanced_inputs(
            runtime.root / "benchmarks/artifacts/task39extra/v6_recursive/g0_inventory.json")
        item = inputs["inputs"]["A2R160"]
        p6_space = common["levels"]["spaces"][6]
        current_map = native_map_arrays(p6_space, common["levels"]["floquets"][6])
        map_identity = compare_native_map_identity(
            current_map,
            inputs["maps"][6],
            context="Q3 p6 balanced input/fresh native map",
        )
        indices = np.asarray(current_map["independent_indices"], dtype=np.int64)
        if item["q"].shape != indices.shape or item["e"].shape != indices.shape:
            raise ValueError("Q3 p6 balanced input has an incompatible active layout")
        e = _new_storage_vector(p6_space)
        q = _new_storage_vector(p6_space)
        e.set(0)
        q.set(0)
        e.array[indices], q.array[indices] = item["e"], item["q"]
        ae = apply_owned(common["fine"]["physical_action"], e)
        q_norm = max(float(q.norm()), np.finfo(float).tiny)
        bridge = float(np.linalg.norm(ae.array[indices] - item["q"])) / q_norm
        runtime.marker("q3_balanced_p6_input_complete", {
            "name": "A2R160", "q_bridge_relative": bridge,
            "e1_audit_sha256": inputs["e1_audit_sha256"],
            "map_identity": map_identity,
            "q": _q3_array_summary(item["q"]), "e": _q3_array_summary(item["e"]),
        })
        if not np.isfinite(bridge) or bridge > 1e-10:
            raise ValueError("Q3 frozen q differs from actual A6 e")
        # e is used only for this input identity check, never by the PC.
        ae.destroy()
        e.destroy()
        ae = e = None
        with _v14_balanced_adapter(runtime, common, fint, capture_vectors=True) as (pc, positive):
            fint_before = int(fint.apply_count)
            h6_before = int(positive["h6"].apply_count)
            runtime.begin_pc(1)
            try:
                z = pc.apply(q)
            except BaseException:
                runtime.finish_pc(completed=False)
                raise
            pc_finish = runtime.finish_pc()
            az = apply_owned(common["fine"]["physical_action"], z)
            output_relative = float(np.linalg.norm(q.array - az.array)) / q_norm
            balance = pc.last_apply_facts["inexact_balance"]
            closure = balance["audit"]
            counts = dict(pc.last_apply_facts["counts"])
            expected_counts = dict(C=2, smoother=1, A_structure=2,
                                   A_inner_true=0, PH_audit=0)
            calls = pc.coarse_calls
            work = []
            for call in calls:
                facts = call["interface_facts"]
                operation_audit = _q3_interface_operation_audit(facts, 42)
                internal = np.asarray(facts["factor_solve_delta"])
                local = np.asarray(facts["local_patch_solve_delta"])
                valid = bool(
                    internal.shape == (42,) and local.shape == (42,)
                    and operation_audit["passed"]
                )
                work.append({
                    "internal_backsolves": int(internal.sum()),
                    "local_backsolves": int(local.sum()),
                    "coarse_solves": int(facts["coarse_solve_count"]),
                    "operation_audit": operation_audit,
                    "passed": valid,
                })
            fint_delta = int(fint.apply_count) - fint_before
            h6_delta = int(positive["h6"].apply_count) - h6_before
            passed = bool(
                len(work) == 2 and all(row["passed"] for row in work)
                and counts == expected_counts and fint_delta == 2 and h6_delta == 1
                and pc.native_A4_count == 2 and balance["actual_audit"] == "PASS"
                and np.isfinite(closure["closure_relative"])
                and closure["closure_relative"] <= 1e-8
                and np.isfinite(output_relative)
            )
            facts = {
                "schema": "task039extra.v14.q3.balanced-p6-audit.v2",
                "input_name": "A2R160", "q_bridge_relative": bridge,
                "pc": pc.last_apply_facts, "pc_finish": pc_finish,
                "coarse_calls": calls, "work": work,
                "pc_counts": counts, "pc_counts_expected": expected_counts,
                "fint_apply_delta": fint_delta, "h6_apply_delta": h6_delta,
                "native_A4_action_count": pc.native_A4_count,
                "identity_A6_action_count": 1, "output_A6_action_count": 1,
                "ledger_A6_action_count": pc.ledger.A_count,
                "ledger_PH_action_count": pc.ledger.PH_count,
                "g2_source": "P64^H A6 H6(q-A6 P64 Fint(P64^H q))",
                "closure": closure, "output_residual_relative": output_relative,
                "passed": passed, "completed": True,
            }
            packet_arrays = {
                "q": q.array.copy(), "z": z.array.copy(), "A6z": az.array.copy(),
                "eps_difference": pc.ledger.last["difference"].array.copy(),
                **pc.last_apply_vectors,
            }
            for index, call in enumerate(pc.ledger.last["call_vectors"], 1):
                for name in ("g", "applied", "eps"):
                    packet_arrays[f"{name}{index}"] = call[name].array.copy()
            packet = _save_packet(
                runtime.directory / "q3_balanced_p6", "A2R160_BAL_H",
                {"schema": "task039extra.v14.q3-balanced-p6-packet.v2",
                 "facts": facts, **packet_arrays}, runtime=runtime)
            facts["packet"] = packet
            runtime.marker("q3_balanced_p6_audit_complete", facts)
            return facts
    except BaseException as exc:
        _save_packet(
            runtime.directory / "q3_balanced_p6", "A2R160_BAL_H_failure",
            {"error": {"type": type(exc).__name__, "message": str(exc)},
             "coarse_calls": [] if pc is None else pc.coarse_calls},
            runtime=runtime)
        raise
    finally:
        for vector in (az, z, ae, q, e):
            if vector is not None:
                vector.destroy()
        runtime.release_workspace("q3_balanced_inputs")


@contextmanager
def _v14_interface_live_stack(
    runtime: _V14Runtime,
    common: dict[str, Any],
    resolved_payload: Mapping[str, Any],
    *,
    stage: str,
    stage_started_monotonic: float | None = None,
):
    """Build the shared matrix-free interface stack and own one cleanup path.

    Q3, Q4 and Q5 all use the same p4 elimination, local ``J`` factors, paired
    ``P/Q`` directions, small ``E`` factor and ``F_int`` adapter.  This context
    keeps those allocations alive only for the stage that uses them and makes
    the explicit ``S_V``/active-volume release and generic internal-factor
    cleanup identical for the diagnostic and fresh p6 paths.
    """

    from src.solvers.physical_interface_schur import (
        InterfaceFintAdapter,
        build_interface_candidate_directions,
        build_interface_coarse_pair,
        build_interface_local_smoother,
        build_interface_partition,
        build_physical_interface_schur,
        interface_patch_rows_from_core,
        orthonormalize_paired_directions,
        _submatrix,
    )

    stage = str(stage)
    if stage not in {"Q3_INTERFACE_CONTROL", "Q4_ORIGINAL", "Q5_NOTCH"}:
        raise ValueError(f"unsupported live interface stack stage {stage!r}")
    prefix = {
        "Q3_INTERFACE_CONTROL": "q3",
        "Q4_ORIGINAL": "q4",
        "Q5_NOTCH": "q5",
    }[stage]
    label = lambda suffix: f"{prefix}_{suffix}"
    storage_rows = int(common["p4"]["dtn_action"].carrier.global_rows)
    if storage_rows != 53084:
        raise ValueError(f"V14 p4 carrier storage rows changed: {storage_rows}")

    full_volume = active_volume = storage_template = None
    core = smoother = coarse_pair = fint = paired = None
    raw_P = raw_Q = None
    reserved_labels: set[str] = set()
    reserved_workspaces: set[str] = set()
    stage_start = (
        time.monotonic()
        if stage_started_monotonic is None
        else float(stage_started_monotonic)
    )
    resources = runtime.contract["resources"]
    stage_budget = resources.get("stage_budgets", {}).get(stage, {})
    workflow_limit = float(stage_budget.get("workflow_seconds", 0.0))
    reserved_workflow = float(getattr(runtime, "workflow_reserved_seconds", 0.0))
    workflow_limit = min(workflow_limit, reserved_workflow)
    if workflow_limit <= 0.0:
        raise ValueError(f"{stage} parent workflow reservation is invalid")

    def workflow_elapsed() -> tuple[float, dict[str, Any]]:
        interval_method = getattr(runtime, "workflow_clock_interval", None)
        if not callable(interval_method):
            raise RuntimeError("V14 live stack requires the parent workflow clock")
        interval = dict(interval_method())
        elapsed = float(interval["budget_seconds"])
        if not np.isfinite(elapsed) or elapsed < 0.0:
            raise RuntimeError("V14 workflow clock interval is not finite")
        return elapsed, interval

    time_policy = normalize_v14_time_policy(getattr(runtime, "time_policy", None))
    workflow_time_observation: dict[str, Any] | None = None
    setup_budget_facts: dict[str, Any] | None = None

    def performance_stop(message: str) -> None:
        nonlocal workflow_time_observation
        elapsed, _interval = workflow_elapsed()
        workflow_time_observation = v14_time_gate_facts(
            elapsed, workflow_limit, time_policy, inclusive=True
        )
        if setup_budget_facts is not None:
            setup_budget_facts["workflow_time_gate"] = dict(workflow_time_observation)
            setup_budget_facts["workflow_time_boundary_message"] = message
        if time_policy == V14_TIME_POLICY_OBSERVE_ONLY:
            return
        raise V14ResourceStop(
            message,
            classification="PERFORMANCE_CONTROLLED_STOP",
        )

    try:
        carrier = common["p4"]["dtn_action"].carrier
        runtime.set_phase("assembly")
        full_label = label("full_volume")
        active_label = label("active_volume")
        vgg_label = label("V_GG")
        sv_label = label("S_V")
        full_volume = _assemble_volume(
            runtime, common, inventory_label=full_label
        )
        reserved_labels.add(full_label)
        partition, port_data = build_interface_partition(
            common["levels"]["spaces"][4],
            common["levels"]["floquets"][4],
            carrier,
            volume=full_volume,
        )
        runtime.marker(f"{prefix}_partition_complete", partition.audit())
        full_info = full_volume.getInfo()
        full_rows = int(full_volume.getSize()[0])
        full_payload = _sparse_payload_bytes(full_info, full_rows)
        runtime.check_projected(active_label, full_payload)
        runtime.reserve_inventory(
            active_label,
            {"matrix_payload_upper_bytes": full_payload},
            check_rss=False,
        )
        reserved_labels.add(active_label)
        storage_template = full_volume.createVecRight()
        active_volume = _submatrix(full_volume, partition.active_full_indices)
        active_info = active_volume.getInfo()
        active_payload = _sparse_payload_bytes(
            active_info, int(active_volume.getSize()[0])
        )
        runtime.replace_inventory(
            active_label,
            {"matrix_payload_bytes": active_payload},
        )
        full_volume.destroy()
        full_volume = None
        runtime.release_inventory(full_label)
        reserved_labels.discard(full_label)

        def allocation_gate(allocation_label: str, facts: Mapping[str, Any]) -> None:
            if allocation_label == "V_GG":
                allocation = int(facts["matrix_payload_bytes"])
                runtime.check_projected(vgg_label, allocation)
                runtime.reserve_inventory(
                    vgg_label,
                    {"matrix_payload_upper_bytes": allocation},
                    check_rss=False,
                )
                reserved_labels.add(vgg_label)
                return
            if allocation_label.startswith("internal_coupling_"):
                block = int(facts["block_index"])
                coupling = int(facts["coupling_bytes"])
                index_bytes = int(facts["index_bytes"])
                workspace = int(facts["workspace_bytes"])
                runtime.check_inventory_projected(
                    label(f"internal_{block}"), coupling + index_bytes + workspace
                )
                runtime.check_projected(
                    label(f"internal_coupling_{block}"),
                    coupling + index_bytes,
                    workspace_bytes=workspace,
                )
                return
            if allocation_label == "S_V":
                allocation = int(facts["matrix_payload_bytes"])
                workspace = int(facts.get("workspace_bytes", 0))
                runtime.check_projected(
                    sv_label, allocation, workspace_bytes=workspace
                )
                runtime.reserve_inventory(
                    sv_label,
                    {"matrix_payload_upper_bytes": allocation},
                    check_rss=False,
                )
                reserved_labels.add(sv_label)
                if workspace:
                    sv_workspace = label("S_V_assembly")
                    runtime.reserve_workspace(sv_workspace, workspace)
                    reserved_workspaces.add(sv_workspace)
                return
            raise ValueError(
                f"unexpected {stage} Schur allocation gate: {allocation_label}"
            )

        before, after = _factor_gates(runtime, local_limit=True)
        core = build_physical_interface_schur(
            active_volume,
            partition,
            carrier,
            port_data=port_data,
            resource_sample=lambda: runtime.sample(f"{prefix}_internal_factor"),
            marker=runtime.marker,
            pre_numeric_gate=before,
            post_numeric_gate=after,
            allocation_gate=allocation_gate,
            owns_volume=True,
            build_interface_matrix=False,
        )
        active_volume = None
        for workspace_label in tuple(reserved_workspaces):
            runtime.release_workspace(workspace_label)
            reserved_workspaces.discard(workspace_label)
        runtime.replace_inventory(
            vgg_label,
            {
                "matrix_payload_bytes": _sparse_payload_bytes(
                    core.V_GG.getInfo(), int(core.V_GG.getSize()[0])
                )
            },
        )
        runtime.replace_inventory(
            sv_label,
            {
                "matrix_payload_bytes": _sparse_payload_bytes(
                    core.S_V.getInfo(), int(core.S_V.getSize()[0])
                )
            },
        )
        runtime.marker(
            f"{prefix}_local_core_complete",
            {
                "partition": partition.audit(),
                "internal_factor_count": len(core.internal),
                "factor_inventory": core.factor_facts,
                "interface_matrix_built": False,
            },
        )
        core.release_owned_volume()
        runtime.release_inventory(active_label)
        reserved_labels.discard(active_label)

        patch_rows = interface_patch_rows_from_core(
            core,
            common["levels"]["spaces"][4],
            common["levels"]["floquets"][4],
        )
        largest_patch, dtn_patch, representative_facts = _q3_representative_patches(
            patch_rows, core.port_data
        )
        runtime.marker(
            f"{prefix}_representative_patches_selected", representative_facts
        )
        delta_gamma, delta_facts = _q3_delta_from_unweighted_p4_mass(
            runtime, common, partition, resolved_payload
        )
        all_deltas = {
            patch_id: delta_gamma[patch_rows[patch_id]]
            for patch_id in range(len(patch_rows))
        }
        remaining_patch_ids = tuple(
            patch_id
            for patch_id in range(len(patch_rows))
            if patch_id not in {largest_patch, dtn_patch}
        )
        process_order = (largest_patch, dtn_patch, *remaining_patch_ids)
        local_factor_cap = int(
            resources["local_factor_matrix_and_allocated_cap_bytes"]
        )
        shared_temp_cap = int(resources["shared_temp_workspace_cap_bytes"])
        scalar_bytes = np.dtype(np.complex128).itemsize
        index_bytes = np.dtype(np.int64).itemsize
        local_factor_patch_upper = [
            int(
                2 * rows.size * rows.size * scalar_bytes
                + 3 * rows.size * index_bytes
            )
            for rows in patch_rows
        ]
        local_factor_upper = int(sum(local_factor_patch_upper))
        local_workspace = max(
            int(
                3 * rows.size * rows.size * scalar_bytes
                + 3 * rows.size * scalar_bytes
                + rows.size * index_bytes
            )
            for rows in patch_rows
        )
        paired_svd_workspace = max(
            int(
                12 * rows.size * rows.size * scalar_bytes
                + 8 * rows.size * scalar_bytes
            )
            for rows in patch_rows
        )
        local_workspace = max(local_workspace, paired_svd_workspace)
        if max(local_factor_patch_upper) > local_factor_cap:
            raise V14ResourceStop(
                f"{stage} one local factor matrix inventory exceeds 512MiB: "
                f"{max(local_factor_patch_upper)} > {local_factor_cap}"
            )
        runtime.check_inventory_projected(label("local_smoother"), local_factor_upper)
        runtime.check_projected(
            label("local_smoother"),
            local_factor_upper,
            workspace_bytes=local_workspace,
        )

        q3_setup = stage == "Q3_INTERFACE_CONTROL"
        q3_known_future_controls = {
            "three_fint_admission_seconds_upper": 45.0,
            "balanced_pc_hard_seconds": float(resources["pc_hard_seconds"]),
            "candidate_S_action_count_upper": 496,
            "candidate_S_action_seconds": "unknown",
            "mgs_seconds": "unknown",
            "packet_save_seconds": "unknown",
            "classification": "known_limits_plus_unmeasured_components",
        }
        known_future_seconds = (
            float(q3_known_future_controls["three_fint_admission_seconds_upper"])
            + float(q3_known_future_controls["balanced_pc_hard_seconds"])
            if q3_setup
            else 0.0
        )
        if q3_setup:
            representative_limit = 900.0
            if workflow_elapsed()[0] + known_future_seconds >= workflow_limit:
                performance_stop(
                    "Q3 local setup has no remaining workflow time after known controls"
                )
        else:
            representative_limit = None
        setup_budget_facts = {
            "schema": "task039extra.v14.interface-local-setup-budget.v2",
            "stage": stage,
            "workflow_clock_source": getattr(
                runtime, "workflow_clock_source", "parent_attempt.workflow_clock_start"
            ),
            "workflow_clock_start": dict(
                getattr(runtime, "workflow_clock_start", {})
            ),
            "reserved_workflow_seconds": reserved_workflow,
            "workflow_limit_seconds": workflow_limit,
            **v14_time_policy_facts(time_policy),
            "workflow_time_gate": workflow_time_observation,
            "known_future_controls": q3_known_future_controls
            if q3_setup
            else {"classification": "not_applied_to_fresh_p6_stage"},
            "known_future_controls_seconds": known_future_seconds,
            "representative_patch_ids": [largest_patch, dtn_patch],
            "process_order": list(process_order),
            "elapsed_before_local_setup_seconds": workflow_elapsed()[0],
            "prediction": None,
        }
        completed_representatives: set[int] = set()
        representative_started_local: dict[int, float] = {}
        representative_durations: dict[int, float] = {}
        representative_ids = (largest_patch, dtn_patch)

        def local_progress(progress: Mapping[str, Any]) -> None:
            event = str(progress["event"])
            patch_id = int(progress["patch_id"])
            local_elapsed = float(progress["elapsed_seconds"])
            stage_elapsed, stage_clock = workflow_elapsed()
            setup_budget_facts["last_stage_elapsed_seconds"] = stage_elapsed
            setup_budget_facts["last_workflow_clock_interval"] = stage_clock
            setup_budget_facts["last_local_builder_elapsed_seconds"] = local_elapsed
            runtime.sample(f"{prefix}_local_patch_{patch_id}_{event}")
            if stage_elapsed >= workflow_limit:
                performance_stop(
                    f"{stage} workflow reached its configured budget during local setup"
                )
            if q3_setup:
                if stage_elapsed + known_future_seconds >= workflow_limit:
                    performance_stop(
                        "Q3 local setup exhausted the known future-control budget"
                    )
                if patch_id not in representative_ids:
                    return
                if event == "patch_started":
                    representative_started_local[patch_id] = local_elapsed
                elif event == "patch_completed":
                    started_local = representative_started_local.get(patch_id)
                    if started_local is None:
                        raise RuntimeError(
                            f"Q3 representative patch {patch_id} completed before it started"
                        )
                    representative_durations[patch_id] = max(
                        0.0, local_elapsed - started_local
                    )
                    completed_representatives.add(patch_id)
                    representative_elapsed = float(
                        sum(representative_durations.values())
                    )
                    if representative_elapsed >= float(representative_limit):
                        performance_stop(
                            "Q3 representative local setup reached its 900-second budget"
                        )
                    if len(completed_representatives) == len(representative_ids):
                        prediction = _q3_local_setup_prediction(
                            patch_rows,
                            process_order,
                            representative_ids,
                            representative_durations,
                        )
                        prediction.update(
                            {
                                "stage_elapsed_at_representatives_seconds": stage_elapsed,
                                "elapsed_before_local_setup_seconds": max(
                                    0.0, stage_elapsed - local_elapsed
                                ),
                                "known_future_controls_seconds": known_future_seconds,
                                "predicted_workflow_total_seconds": (
                                    max(0.0, stage_elapsed - local_elapsed)
                                    + prediction["predicted_local_setup_seconds"]
                                    + known_future_seconds
                                ),
                            }
                        )
                        prediction[
                            "remaining_workflow_after_predicted_setup_and_known_controls_seconds"
                        ] = workflow_limit - prediction["predicted_workflow_total_seconds"]
                        setup_budget_facts["prediction"] = prediction
                        runtime.marker(f"{prefix}_local_setup_prediction", prediction)
                        if prediction[
                            "remaining_workflow_after_predicted_setup_and_known_controls_seconds"
                        ] <= 0.0:
                            performance_stop(
                                "Q3 predicted complete local setup leaves no time for known controls"
                            )

        local_workspace_label = label("local_smoother_build")
        runtime.reserve_workspace(local_workspace_label, local_workspace)
        reserved_workspaces.add(local_workspace_label)
        smoother = build_interface_local_smoother(
            core.S_V,
            patch_rows,
            port_data=core.port_data,
            ambient_rows=partition.gamma_rows,
            max_rows=2048,
            max_workspace_bytes=local_factor_cap,
            paired_basis_workspace_bytes=shared_temp_cap,
            solve_rtol=1.0e-10,
            paired_patch_deltas=all_deltas,
            process_order=process_order,
            progress_callback=local_progress,
        )
        runtime.release_workspace(local_workspace_label)
        reserved_workspaces.discard(local_workspace_label)
        local_audit = smoother.audit()
        final_setup_elapsed, _final_setup_clock = workflow_elapsed()
        workflow_time_observation = v14_time_gate_facts(
            final_setup_elapsed, workflow_limit, time_policy, inclusive=True
        )
        setup_budget_facts.update(
            {
                "completed": True,
                "measured_local_builder_seconds": float(
                    local_audit["build_elapsed_seconds"]
                ),
                "stage_elapsed_after_local_setup_seconds": workflow_elapsed()[0],
                "workflow_time_gate": workflow_time_observation,
            }
        )
        setup_budget_facts["workflow_remaining_after_local_setup_seconds"] = (
            workflow_limit - setup_budget_facts["stage_elapsed_after_local_setup_seconds"]
        )
        runtime.marker(f"{prefix}_local_setup_budget_complete", setup_budget_facts)
        if q3_setup and (
            setup_budget_facts["stage_elapsed_after_local_setup_seconds"]
            + known_future_seconds
            >= workflow_limit
        ):
            performance_stop(
                "Q3 completed local setup without enough time for known controls"
            )
        local_resident_bytes = int(
            local_audit["retained_factor_bytes"]
            + local_audit["retained_paired_basis_bytes"]
        )
        local_label = label("local_smoother")
        runtime.check_inventory_projected(local_label, local_resident_bytes)
        runtime.reserve_inventory(
            local_label,
            {
                "retained_factor_bytes": int(local_audit["retained_factor_bytes"]),
                "retained_paired_basis_bytes": int(
                    local_audit["retained_paired_basis_bytes"]
                ),
            },
            check_rss=False,
        )
        reserved_labels.add(local_label)
        if sorted(smoother.paired_bases) != list(range(len(patch_rows))):
            raise RuntimeError(
                f"{stage} local builder did not produce all local SVD bases"
            )
        runtime.marker(
            f"{prefix}_local_smoother_complete",
            {
                "patch_rows": [int(rows.size) for rows in patch_rows],
                "representatives": representative_facts,
                "delta": delta_facts,
                "process_order": list(process_order),
                "local_factor_cap_bytes": local_factor_cap,
                "local_factor_cap_scope": "per_patch_matrix_plus_LU",
                "local_factor_patch_upper_bytes": local_factor_patch_upper,
                "shared_temp_cap_bytes": shared_temp_cap,
                "local_factor_upper_bytes": local_factor_upper,
                "local_workspace_upper_bytes": local_workspace,
                "setup_budget": setup_budget_facts,
                "audit": local_audit,
            },
        )

        action_checks = _q3_action_checks(runtime, core, common, storage_template)
        if not action_checks["passed"]:
            raise RuntimeError(
                f"{stage} explicit/matrix-free action gate failed: {action_checks}"
            )

        candidate_workspace_label = label("candidate_mgs_coarse")

        def candidate_preallocation(facts: Mapping[str, Any]) -> None:
            workspace = int(facts["workspace_upper_bytes"])
            if workspace > shared_temp_cap:
                raise V14ResourceStop(
                    f"{stage} candidate/MGS/coarse temporary workspace exceeds 1GiB: "
                    f"{workspace} > {shared_temp_cap}"
                )
            runtime.check_workspace_projected(candidate_workspace_label, workspace)
            runtime.marker(f"{prefix}_candidate_preallocation_gate", dict(facts))
            runtime.reserve_workspace(candidate_workspace_label, workspace)
            reserved_workspaces.add(candidate_workspace_label)

        raw_P, raw_Q, candidate_mapping, candidate_facts = (
            build_interface_candidate_directions(
                patch_rows,
                smoother.paired_bases,
                core.port_data,
                delta_gamma,
                max_candidates=496,
                max_mgs_rows=512,
                preallocation_callback=candidate_preallocation,
            )
        )
        if not candidate_facts["all_42_local_bases"]:
            raise RuntimeError(
                f"{stage} candidate construction did not receive all local bases"
            )
        paired = orthonormalize_paired_directions(
            raw_P,
            raw_Q,
            pair_tol=1.0e-12,
            max_pairs=512,
        )
        paired_facts = paired.audit()
        del raw_P, raw_Q
        raw_P = raw_Q = None
        paired_capacity = int(paired_facts["checks"]["output_basis_capacity_bytes"])
        if paired_capacity % 2:
            raise RuntimeError(f"{stage} paired P/Q capacity is not evenly split")
        paired_label = label("paired_basis")
        runtime.check_inventory_projected(paired_label, paired_capacity)
        runtime.reserve_inventory(
            paired_label,
            {
                "P_capacity_bytes": paired_capacity // 2,
                "Q_capacity_bytes": paired_capacity // 2,
            },
            check_rss=False,
        )
        reserved_labels.add(paired_label)
        runtime.marker(
            f"{prefix}_paired_candidates_complete",
            {
                "candidate": candidate_facts,
                "paired": paired_facts,
                "mapping": candidate_mapping,
            },
        )
        if paired.rank == 0:
            raise np.linalg.LinAlgError(
                "COARSE_PAIR_UNSTABLE: paired candidate rank is zero"
            )
        coarse_bound = int(
            3 * paired.rank * paired.rank * np.dtype(np.complex128).itemsize
            + 3 * paired.rank * np.dtype(np.complex128).itemsize
            + paired.rank * np.dtype(np.int64).itemsize
        )
        coarse_label = label("coarse_pair")
        runtime.check_inventory_projected(coarse_label, coarse_bound)
        runtime.check_projected(coarse_label, coarse_bound)

        # Keep only V_GG, couplings, local factors and the carrier for the
        # matrix-free route.  S_V and the active sparse volume are construction
        # objects and must be gone before the coarse action is formed.
        core.release_explicit_schur()
        runtime.release_inventory(sv_label)
        reserved_labels.discard(sv_label)
        runtime.release_inventory(active_label)
        reserved_labels.discard(active_label)
        coarse_pair = build_interface_coarse_pair(
            core.apply_physical_schur_block,
            paired.P,
            paired.Q,
            max_rows=512,
            max_workspace_bytes=int(resources["interface_workspace_cap_bytes"]),
            max_temp_workspace_bytes=shared_temp_cap,
            rcond_rtol=1.0e-12,
            solve_rtol=1.0e-10,
        )
        if candidate_workspace_label in reserved_workspaces:
            runtime.release_workspace(candidate_workspace_label)
            reserved_workspaces.discard(candidate_workspace_label)
        coarse_resident_bytes = int(
            coarse_pair.E.nbytes
            + coarse_pair.lu.nbytes
            + coarse_pair.pivots.nbytes
        )
        runtime.check_inventory_projected(coarse_label, coarse_resident_bytes)
        runtime.reserve_inventory(
            coarse_label,
            {
                "E_bytes": int(coarse_pair.E.nbytes),
                "LU_bytes": int(coarse_pair.lu.nbytes),
                "pivots_bytes": int(coarse_pair.pivots.nbytes),
            },
            check_rss=False,
        )
        reserved_labels.add(coarse_label)
        fint = InterfaceFintAdapter(core, smoother, coarse_pair)
        stack = {
            "schema": "task039extra.v14.live-interface-stack.v1",
            "stage": stage,
            "prefix": prefix,
            "partition": partition,
            "port_data": port_data,
            "storage_template": storage_template,
            "core": core,
            "local_smoother": smoother,
            "coarse_pair": coarse_pair,
            "fint": fint,
            "patch_rows": patch_rows,
            "delta_gamma": delta_gamma,
            "delta_facts": delta_facts,
            "representative_facts": representative_facts,
            "local_audit": local_audit,
            "setup_budget": setup_budget_facts,
            "action_checks": action_checks,
            "candidate_mapping": candidate_mapping,
            "candidate_facts": candidate_facts,
            "paired_facts": paired_facts,
            "local_factor_patch_upper_bytes": local_factor_patch_upper,
            "local_factor_upper_bytes": local_factor_upper,
            "local_workspace_upper_bytes": local_workspace,
            "coarse_bound_bytes": coarse_bound,
            "q3_stage_start_monotonic": stage_start,
            **v14_time_policy_facts(time_policy),
        }
        runtime.marker(
            f"{prefix}_live_interface_stack_ready",
            {
                "schema": stack["schema"],
                "stage": stage,
                "internal_factor_count": len(core.internal),
                "gamma_rows": int(partition.gamma_rows),
                "paired_rank": int(paired.rank),
                "global_interface_matrix_built": False,
                "global_dense_schur_constructed": False,
            },
        )
        yield stack
    finally:
        for workspace_label in tuple(reserved_workspaces):
            runtime.release_workspace(workspace_label)
        if raw_P is not None:
            del raw_P
        if raw_Q is not None:
            del raw_Q
        if fint is not None:
            fint.destroy()
        if coarse_pair is not None:
            coarse_pair.destroy()
        paired = None
        if smoother is not None:
            smoother.destroy()
        if core is not None:
            core.destroy()
        elif active_volume is not None:
            active_volume.destroy()
        if full_volume is not None:
            full_volume.destroy()
        if storage_template is not None:
            storage_template.destroy()
        for label_name in tuple(reserved_labels):
            runtime.release_inventory(label_name)
        for label_name in (
            label("coarse_pair"),
            label("paired_basis"),
            label("local_smoother"),
            label("S_V"),
            label("V_GG"),
            label("active_volume"),
            label("full_volume"),
        ):
            runtime.release_inventory(label_name)
        # _factor_gates registers internal factors under their solver labels;
        # release every such label even if construction stopped halfway through
        # the 42-block sequence.
        for label_name in tuple(runtime.inventory_entries):
            if str(label_name).startswith("internal_"):
                runtime.release_inventory(label_name)


def _q3_interface_control(
    runtime: _V14Runtime,
    common: dict[str, Any],
    rhs_records: list[dict[str, Any]],
    resolved_payload: Mapping[str, Any],
    *,
    stage_started_monotonic: float | None = None,
) -> dict[str, Any]:
    """Exercise the shared live stack against the three reviewed p4 RHSs."""

    with _v14_interface_live_stack(
        runtime,
        common,
        resolved_payload,
        stage="Q3_INTERFACE_CONTROL",
        stage_started_monotonic=stage_started_monotonic,
    ) as stack:
        core = stack["core"]
        smoother = stack["local_smoother"]
        coarse_pair = stack["coarse_pair"]
        fint = stack["fint"]
        partition = stack["partition"]
        storage_template = stack["storage_template"]
        solution_arrays: list[np.ndarray] = []
        solve_records: list[dict[str, Any]] = []
        three_rhs_fint_apply_deltas: list[int] = []
        for reviewed in rhs_records:
            runtime.set_phase("solve")
            runtime.marker("q3_rhs_solve_started", {"stem": reviewed["stem"]})
            started = time.perf_counter()
            rhs = storage_template.copy()
            rhs.array[:] = reviewed["rhs"]
            result = None
            fint_apply_before = int(fint.apply_count)
            try:
                result = fint.solve_intermediate(rhs)
                solution = result["final_solution"]
                residual_decomposition = _physical_residual_decomposition(
                    common["p4"]["physical_action"],
                    rhs,
                    solution,
                    partition,
                )
                applied_array = residual_decomposition.pop("applied_array")
                residual_array = residual_decomposition.pop("residual_array")
                solution_array = np.asarray(solution.array).copy()
                solution_arrays.append(solution_array)
                interface_facts = {
                    key: value for key, value in result.items() if key != "final_solution"
                }
                operation_audit = _q3_interface_operation_audit(
                    interface_facts, len(core.internal)
                )
                operation_count_passed = bool(operation_audit["passed"])
                fint_apply_delta = int(fint.apply_count) - fint_apply_before
                three_rhs_fint_apply_deltas.append(fint_apply_delta)
                solve_record = {
                    "stem": reviewed["stem"],
                    "logical_rhs": reviewed["logical_rhs"],
                    "elapsed_seconds": time.perf_counter() - started,
                    "native_A4_relative_residual": residual_decomposition["total_relative"],
                    "native_A4_residual_decomposition": residual_decomposition,
                    "interface_facts": interface_facts,
                    "operation_audit": operation_audit,
                    "operation_count_passed": operation_count_passed,
                    "fint_apply_count_delta": fint_apply_delta,
                    "solution_sha256": _sha256_bytes(solution_array.tobytes()),
                    "reference_true_residual": reviewed["reference_true_residual"],
                }
                packet = _save_packet(
                    runtime.directory / "q3_rhs_packets",
                    reviewed["stem"],
                    {
                        "schema": "task039extra.v14.q3-rhs-packet.v2",
                        "identity": {
                            key: value
                            for key, value in reviewed.items()
                            if key
                            not in {
                                "rhs",
                                "reference_solution",
                                "reference_A4y",
                                "reference_map",
                            }
                        },
                        "solve": solve_record,
                        "x_storage": solution_array,
                        "A4x_storage": applied_array,
                        "residual_storage": residual_array,
                    },
                    runtime=runtime,
                )
                solve_record["packet"] = packet
                solve_records.append(solve_record)
            finally:
                if result is not None:
                    result["final_solution"].destroy()
                rhs.destroy()
            runtime.sample(f"q3_rhs_{reviewed['stem']}_complete")

        field = _field_metrics(
            runtime,
            common,
            solution_arrays,
            [item["reference_solution"] for item in rhs_records],
        )
        for solve, field_record in zip(solve_records, field, strict=True):
            solve["field_metrics"] = field_record
        max_rho = max(item["native_A4_relative_residual"] for item in solve_records)
        max_field = max(
            max(
                item["field_metrics"]["field_l2_relative"],
                item["field_metrics"]["scaled_curl_relative"],
            )
            for item in solve_records
        )
        admission_by_stem = {}
        for item in solve_records:
            fint_time = v14_time_gate_facts(
                item["elapsed_seconds"],
                15.0,
                normalize_v14_time_policy(getattr(runtime, "time_policy", None)),
            )
            fint_time["gate"] = f"Q3_INTERFACE_CONTROL.fint.{item['stem']}"
            numeric_pass = bool(
                item["native_A4_relative_residual"]
                <= (0.2 if item["stem"].endswith("_02") else 0.5)
                and item["field_metrics"]["field_l2_relative"]
                <= (0.9 if item["stem"].endswith("_02") else 0.5)
                and item["field_metrics"]["scaled_curl_relative"]
                <= (0.9 if item["stem"].endswith("_02") else 0.6)
                and item["operation_count_passed"]
            )
            admission_by_stem[item["stem"]] = {
                "rho": item["native_A4_relative_residual"],
                "eta": item["field_metrics"]["field_l2_relative"],
                "eta_curl": item["field_metrics"]["scaled_curl_relative"],
                "elapsed_seconds": item["elapsed_seconds"],
                "numeric_pass": numeric_pass,
                "time_gate": fint_time,
                "passed": bool(
                    numeric_pass
                    and (
                        not fint_time["time_gate_evaluated"]
                        or not fint_time["exceeded"]
                    )
                ),
            }
        admission_pass = all(item["passed"] for item in admission_by_stem.values())
        three_rhs_fint_count = int(sum(three_rhs_fint_apply_deltas))
        three_rhs_fint_count_passed = bool(
            len(three_rhs_fint_apply_deltas) == len(rhs_records)
            and all(delta == 1 for delta in three_rhs_fint_apply_deltas)
        )
        pre_balanced_packet = _save_packet(
            runtime.directory / "q3_rhs_packets",
            "three_rhs_complete_before_balanced_audit",
            {
                "schema": "task039extra.v14.q3-three-rhs-complete.v1",
                "solve_records": solve_records,
                "admission": admission_by_stem,
                "three_rhs_fint_apply_deltas": three_rhs_fint_apply_deltas,
                "three_rhs_fint_apply_count": three_rhs_fint_count,
                "three_rhs_fint_apply_count_passed": three_rhs_fint_count_passed,
                "max_native_A4_relative_residual": max_rho,
                "max_field_l2_or_scaled_curl": max_field,
            },
            runtime=runtime,
        )
        runtime.marker(
            "q3_three_rhs_complete_before_balanced_audit",
            {"packet": pre_balanced_packet},
        )
        balanced_audit = _q3_balanced_p6_audit(runtime, common, fint)
        stage_pass = bool(
            admission_pass
            and three_rhs_fint_count_passed
            and balanced_audit["passed"]
        )
        record = {
            "schema": "task039extra.v14.q3-interface-control.v2",
            "status": "Q3_INTERFACE_CONTROL_PASS"
            if stage_pass
            else "INTERFACE_CONTROL_UNQUALIFIED",
            "stage_pass": stage_pass,
            "admission_pass": admission_pass,
            "official_result": False,
            "result_classification": (
                "diagnostic_interface_candidate_pass"
                if stage_pass
                else "controlled_negative_interface_candidate"
            ),
            "partition": partition.audit(),
            "core": core.factor_facts,
            "representative_patches": stack["representative_facts"],
            "delta": stack["delta_facts"],
            "local_smoother": stack["local_audit"],
            "action_checks": stack["action_checks"],
            "candidate": stack["candidate_facts"],
            "paired_basis": stack["paired_facts"],
            "coarse_pair": coarse_pair.audit(),
            "solve_records": solve_records,
            "admission": admission_by_stem,
            "balanced_p6_audit": balanced_audit,
            **v14_time_policy_facts(
                normalize_v14_time_policy(getattr(runtime, "time_policy", None))
            ),
            "three_rhs_complete_packet": pre_balanced_packet,
            "gates": {
                "candidate_input_upper_bound": 496,
                "coarse_rows": 512,
                "coarse_rcond": 1.0e-12,
                "coarse_solve_residual": 1.0e-10,
                "difficult_rho": 0.5,
                "difficult_eta": 0.5,
                "difficult_eta_curl": 0.6,
                "feedback_rho": 0.2,
                "feedback_eta": 0.9,
                "feedback_eta_curl": 0.9,
                "single_fint_seconds": 15.0,
                "time_policy": normalize_v14_time_policy(
                    getattr(runtime, "time_policy", None)
                ),
                "time_gate_evaluated": normalize_v14_time_policy(
                    getattr(runtime, "time_policy", None)
                )
                == V14_TIME_POLICY_ENFORCE,
                "max_native_A4_relative_residual": max_rho,
                "max_field_l2_or_scaled_curl": max_field,
                "three_rhs_fint_apply_deltas": three_rhs_fint_apply_deltas,
                "three_rhs_fint_apply_count": three_rhs_fint_count,
                "three_rhs_fint_apply_expected": len(rhs_records),
                "three_rhs_fint_apply_count_passed": three_rhs_fint_count_passed,
            },
            "lifecycle": {
                "global_interface_matrix_built": False,
                "global_interface_factor_built": False,
                "global_dense_schur_constructed": False,
                "explicit_S_V_released_before_candidate_solves": True,
                "internal_factor_count": len(core.internal),
                "fint_apply_count": fint.apply_count,
                "three_rhs_fint_apply_deltas": three_rhs_fint_apply_deltas,
                "three_rhs_fint_apply_count": three_rhs_fint_count,
                "three_rhs_fint_apply_count_expected": len(rhs_records),
                "fint_apply_count_expected_after_balanced_audit": len(rhs_records) + 2,
                "local_smoother": smoother.audit(),
                "coarse_pair": coarse_pair.audit(),
                "inventory_peak_bytes": runtime.inventory_peak_bytes,
                "workspace_peak_bytes": runtime.workspace_peak_bytes,
            },
        }
        runtime.marker("q3_interface_control_complete", record)
        return record


def _v14_physical_checks(
    solver, field, comparison, *, time_policy=V14_TIME_POLICY_ENFORCE
) -> dict[str, bool]:
    """Apply the unchanged physical gates to recorded numerical quantities."""

    from src.runners.physical_macro_v12 import (
        _SELECTED_FIELD_COORDINATE_KEYS, _SELECTED_FIELD_VALUE_KEYS,
    )

    def bounded(value, limit):
        return bool(np.isfinite(value) and 0 <= value <= limit)

    current, reference = comparison["current"], comparison["reference"]
    modal, selected = comparison["modal"], comparison["selected_field"]
    normalized_policy = normalize_v14_time_policy(time_policy)
    solve_seconds = float(solver["elapsed_seconds"])
    checks = {
        "A6": bounded(solver["final_true_residual"], 1e-6),
        "single_zero_start_FGMRES32": (
            solver["ksp_create_count"] == solver["ksp_solve_count"] == 1
            and solver["restart"] == 32 and solver["max_it"] == 2048
            and solver["zero_start"] is True),
        "solve_time": bool(
            np.isfinite(solve_seconds)
            and solve_seconds >= 0.0
            and (
                normalized_policy == V14_TIME_POLICY_OBSERVE_ONLY
                or solve_seconds <= 10800.0
            )
        ),
        "mode_count": modal["mode_count"] == 80,
        "mode_amplitudes": bounded(modal["amplitude_relative_difference"], 1e-4),
        "mode_powers": bounded(modal["power_max_absolute_difference"], 1e-6),
        "no_phase_fit": modal["phase_fitting"] is False,
        "coordinates": all(selected["coordinates"][key]["exact"] is True
                           for key in _SELECTED_FIELD_COORDINATE_KEYS),
    }
    for name in ("L2", "scaled_curl"):
        value = field[name]
        ratio = value["absolute_error_norm"] / max(value["reference_norm"], np.finfo(float).tiny)
        checks[name] = bounded(ratio, 1e-4)
    for name in ("R", "T", "A", "A_volume"):
        checks[name] = bounded(abs(current[name] - reference[name]), 1e-5)
    checks["energy_conservation"] = bounded(abs(current["R"] + current["T"] + current["A_volume"] - 1.), 1e-5)
    checks["absorption_consistency"] = bounded(abs(current["A"] - current["A_volume"]), 1e-5)
    for name in _SELECTED_FIELD_VALUE_KEYS:
        value = selected["differences"][name]
        checks[name] = bool(bounded(value["relative"], 1e-4) or (
            bounded(value["reference_norm"], 1e-12) and bounded(value["max_absolute"], 1e-10)))
    for name in ("electric_finite", "magnetic_finite", "auxiliary_finite", "curl_postprocess_success"):
        checks[name] = comparison["finite"][name] is True
    return checks


def _v21_authority_limited_checks(
    solver_facts: Mapping[str, Any], output: Mapping[str, Any],
    *, post_release_relative: float | None,
    common: Mapping[str, Any] | None = None,
    output_dir: Path | None = None,
) -> tuple[dict[str, bool], dict[str, Any]]:
    """Check B/C outputs without inventing a missing reference comparison.

    The channel files are read back from disk and compared with the live
    80-mode inventory.  This keeps the authority-limited branch independent
    of the worker's aggregate status fields and catches a dropped/reordered
    mode, nonfinite amplitude, bad normalization, or a negative modal power.
    """

    port = output.get("port_metrics", {})
    volume = output.get("volume_metrics", {})
    values = {
        "R": float(port.get("R_total", np.nan)),
        "T": float(port.get("T_total", np.nan)),
        "A": float(port.get("A_balance", np.nan)),
        "A_volume": float(volume.get("A_volume_total", np.nan)),
    }
    closure = {
        "A_minus_A_volume": abs(values["A"] - values["A_volume"]),
        "R_plus_T_plus_A_volume_minus_one": abs(
            values["R"] + values["T"] + values["A_volume"] - 1.0
        ),
        "R_plus_T_minus_modal": abs(
            float(port.get("R_plus_T", np.nan)) - values["R"] - values["T"]
        ),
    }
    evaluation = solver_facts.get("final_evaluation", {})
    identity_limits = {
        "port_closure_relative": 1.0e-8,
        "internal_residual_relative": 1.0e-10,
        "native_identity_relative": 1.0e-10,
        "schur_port_identity_relative": 1.0e-10,
    }
    identity_values = {
        key: float(evaluation.get(key, np.nan)) for key in identity_limits
    }
    finite = {
        "power": bool(np.isfinite(list(values.values())).all()),
        "electric": bool(output.get("electric_finite") is True),
        "auxiliary": bool(output.get("auxiliary_finite") is True),
        "magnetic": bool(
            np.isfinite(
                float(output.get("field_export", {}).get("max_abs_H", np.nan))
            )
        ),
        "curl": bool(
            output.get("field_export", {}).get("curl_postprocess_success") is True
        ),
    }
    channel_checks = {
        "files": False,
        "mode_key_order": False,
        "amplitudes_finite": False,
        "powers_finite": False,
        "modal_sums": False,
        "normalization": False,
        "passivity": False,
    }
    channel_facts: dict[str, Any] = {
        "status": "NOT_AVAILABLE",
        "expected_count": 80,
        "checked_count": 0,
        "failure_keys": [],
    }

    def complex_value(value: Any) -> complex:
        if isinstance(value, Mapping):
            return complex(float(value["real"]), float(value["imag"]))
        if isinstance(value, (list, tuple)) and len(value) == 2:
            return complex(float(value[0]), float(value[1]))
        return complex(value)

    if common is not None and output_dir is not None:
        try:
            orders_path = Path(output_dir) / "dtn_port_diffraction_orders_3d.json"
            amplitudes_path = Path(output_dir) / "dtn_auxiliary_amplitudes_3d.json"
            orders_payload = json.loads(orders_path.read_text(encoding="utf-8"))
            amplitude_rows = json.loads(amplitudes_path.read_text(encoding="utf-8"))
            order_rows = orders_payload["orders"]
            expected_modes = list(common["fine"]["modes"])
            expected_keys = [
                (str(mode.side), int(mode.m), int(mode.n), str(mode.polarization))
                for mode in expected_modes
            ]

            def row_key(row: Mapping[str, Any]) -> tuple[str, int, int, str]:
                return (
                    str(row["side"]),
                    int(row["m"]),
                    int(row["n"]),
                    str(row["polarization"]),
                )

            order_keys = [row_key(row) for row in order_rows]
            amplitude_keys = [row_key(row) for row in amplitude_rows]
            order_key_set = set(order_keys)
            amplitude_key_set = set(amplitude_keys)
            unique_keys = (
                len(order_keys) == len(order_key_set)
                and len(amplitude_keys) == len(amplitude_key_set)
            )
            channel_checks["files"] = (
                len(order_rows) == 80
                and len(amplitude_rows) == 80
                and unique_keys
            )
            channel_checks["mode_key_order"] = (
                order_keys == expected_keys and amplitude_keys == expected_keys
            )
            order_by_key = {key: row for key, row in zip(order_keys, order_rows)}
            amplitude_by_key = {
                key: row for key, row in zip(amplitude_keys, amplitude_rows)
            }
            per_channel = []
            amplitude_finite = True
            power_finite = True
            passivity = True
            modal_r = 0.0
            modal_t = 0.0
            failures = []
            for key in expected_keys:
                order = order_by_key.get(key)
                amplitude = amplitude_by_key.get(key)
                if order is None or amplitude is None:
                    failures.append(list(key))
                    continue
                complex_fields = (
                    "auxiliary_amplitude_total_projection",
                    "incident_projection",
                    "outgoing_amplitude",
                    "outgoing_amplitude_at_boundary",
                )
                finite_amplitude = all(
                    np.isfinite(complex_value(order[field]))
                    and np.isfinite(complex_value(amplitude[field]))
                    for field in complex_fields
                )
                finite_power = all(
                    np.isfinite(float(order[field]))
                    for field in ("modal_power_code_units", "power_ratio", "R", "T")
                )
                power_ratio = float(order["power_ratio"])
                r_value = float(order["R"])
                t_value = float(order["T"])
                channel_passive = (
                    power_ratio >= -1.0e-12
                    and r_value >= -1.0e-12
                    and t_value >= -1.0e-12
                )
                same_outgoing = all(
                    abs(
                        complex_value(order[field])
                        - complex_value(amplitude[field])
                    )
                    <= 1.0e-12
                    for field in (
                        "outgoing_amplitude",
                        "outgoing_amplitude_at_boundary",
                    )
                )
                amplitude_finite = amplitude_finite and finite_amplitude and same_outgoing
                power_finite = power_finite and finite_power
                passivity = passivity and channel_passive
                modal_r += r_value
                modal_t += t_value
                if not (finite_amplitude and finite_power and channel_passive and same_outgoing):
                    failures.append(list(key))
                per_channel.append(
                    {
                        "key": list(key),
                        "finite_amplitude": bool(finite_amplitude),
                        "finite_power": bool(finite_power),
                        "power_ratio": power_ratio,
                        "R": r_value,
                        "T": t_value,
                        "outgoing_fields_match": bool(same_outgoing),
                        "passive": bool(channel_passive),
                    }
                )
            metrics_incident = float(port.get("incident_power_code_units", np.nan))
            output_aux = np.asarray(output.get("auxiliary", ()), dtype=np.complex128)
            channel_checks["amplitudes_finite"] = bool(
                len(per_channel) == 80
                and amplitude_finite
                and output_aux.shape == (80,)
                and np.isfinite(output_aux).all()
            )
            channel_checks["powers_finite"] = bool(
                len(per_channel) == 80 and power_finite
            )
            channel_checks["modal_sums"] = bool(
                np.isfinite(modal_r)
                and np.isfinite(modal_t)
                and abs(modal_r - values["R"]) <= 1.0e-8
                and abs(modal_t - values["T"]) <= 1.0e-8
                and abs((modal_r + modal_t) - float(port.get("R_plus_T", np.nan)))
                <= 1.0e-8
            )
            channel_checks["normalization"] = bool(
                np.isfinite(metrics_incident)
                and metrics_incident > 0.0
                and abs(
                    metrics_incident
                    - float(
                        orders_payload.get("metrics", {}).get(
                            "incident_power_code_units", np.nan
                        )
                    )
                )
                <= 1.0e-12 * max(abs(metrics_incident), 1.0)
            )
            channel_checks["passivity"] = bool(
                passivity
                and values["R"] >= -1.0e-12
                and values["T"] >= -1.0e-12
                and values["A_volume"] >= -1.0e-12
                and values["R"] + values["T"] + values["A_volume"]
                <= 1.0 + 1.0e-5
            )
            channel_facts = {
                "status": "CHECKED",
                "expected_count": 80,
                "checked_count": len(per_channel),
                "order_keys": [list(key) for key in order_keys],
                "amplitude_keys": [list(key) for key in amplitude_keys],
                "failure_keys": failures,
                "modal_R": modal_r,
                "modal_T": modal_t,
                "incident_power_code_units": metrics_incident,
                "per_channel": per_channel,
                "files": {
                    "orders": str(orders_path),
                    "amplitudes": str(amplitudes_path),
                },
            }
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            channel_facts = {
                "status": "FAILED_TO_READ_OR_VALIDATE",
                "expected_count": 80,
                "checked_count": 0,
                "failure_keys": [],
                "error": {"type": type(exc).__name__, "message": str(exc)},
            }
    checks = {
        "solver_gate": bool(
            solver_facts.get("status") == "TRUE_RESIDUAL_PASS"
            and np.isfinite(
                float(solver_facts.get("final_true_residual", np.nan))
            )
            and float(solver_facts.get("final_true_residual", np.inf)) <= 1.0e-6
        ),
        "post_release_residual": bool(
            post_release_relative is not None
            and np.isfinite(post_release_relative)
            and post_release_relative <= 1.0e-6
        ),
        "identity": all(
            np.isfinite(identity_values[key])
            and 0.0 <= identity_values[key] <= limit
            for key, limit in identity_limits.items()
        ),
        "power_finite": finite["power"],
        "field_finite": all(finite.values()),
        "energy_closure": bool(
            np.isfinite(closure["R_plus_T_plus_A_volume_minus_one"])
            and closure["R_plus_T_plus_A_volume_minus_one"] <= 1.0e-5
        ),
        "absorption_consistency": bool(
            np.isfinite(closure["A_minus_A_volume"])
            and closure["A_minus_A_volume"] <= 1.0e-5
        ),
        "modal_power_closure": bool(
            np.isfinite(closure["R_plus_T_minus_modal"])
            and closure["R_plus_T_minus_modal"] <= 1.0e-5
        ),
        "channel_files": channel_checks["files"],
        "channel_mode_key_order": channel_checks["mode_key_order"],
        "channel_amplitudes_finite": channel_checks["amplitudes_finite"],
        "channel_powers_finite": channel_checks["powers_finite"],
        "channel_modal_sums": channel_checks["modal_sums"],
        "channel_normalization": channel_checks["normalization"],
        "channel_passivity": channel_checks["passivity"],
    }
    facts = {
        "power": values,
        "closure": closure,
        "identity_values": identity_values,
        "identity_limits": identity_limits,
        "finite": finite,
        "channel_checks": channel_checks,
        "channel_facts": channel_facts,
        "reference_comparison": "NOT_ATTEMPTED_REFERENCE_UNAVAILABLE",
    }
    return checks, facts


def _v14_settled_stage_gate(runtime: _V14Runtime, required: str) -> dict[str, Any]:
    """Use the same settled evidence checks for admission and Q6 reporting."""

    if required not in {"Q1_FULL_DIRECT", "Q2_SCHUR_DIRECT", "Q3_INTERFACE_CONTROL", "Q4_ORIGINAL", "Q5_NOTCH"}:
        raise ValueError(f"unsupported settled V14 stage {required}")
    original = "9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f"
    notch = "7a4d2a797a274fd4a02955647e91288908dd6a457c37984535fa2db9bfec06ec"
    mode = "dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2"
    facts = {"required_stage": required, "qualified": False, "bindings": {}, "checks": {}}

    def load(path):
        data = Path(path).read_bytes()
        facts["bindings"][str(path)] = _sha256_bytes(data)
        return json.loads(data)

    def bounded(value, limit):
        return bool(np.isfinite(value) and 0 <= value <= limit)

    try:
        ledger = load(runtime._ledger_path)
        record = ledger["stages"][required]
        attempt = record["attempts"][-1]
        directory = Path(attempt["run_directory"])
        worker = load(directory / "physical_p4_schur_v14_summary.json")
        manifest = load(directory / "run_manifest.json")
        parent = load(directory / "run_summary.json")
        watchdog = load(directory / "watchdog/summary.json")
        resolved_path = directory / "resolved_config.json"
        resolved = load(resolved_path)
        source = attempt["source_sha"]
        attempt_time_policy = normalize_v14_time_policy(
            attempt.get("time_policy")
        )
        manifest_time_policy = normalize_v14_time_policy(
            manifest.get("v14_time_policy")
        )
        parent_time_policy = normalize_v14_time_policy(
            parent.get("time_policy")
        )
        watchdog_time_policy = normalize_v14_time_policy(
            watchdog.get("time_policy")
        )
        worker_time_policy = normalize_v14_time_policy(
            worker.get("time_policy")
        )
        policy_facts = v14_time_policy_facts(attempt_time_policy)
        facts.update(policy_facts)
        facts["time_policy_sources"] = {
            "attempt": attempt_time_policy,
            "manifest": manifest_time_policy,
            "parent": parent_time_policy,
            "watchdog": watchdog_time_policy,
            "worker": worker_time_policy,
        }
        exact = required in {"Q1_FULL_DIRECT", "Q2_SCHUR_DIRECT"}
        expected_physical = notch if required == "Q5_NOTCH" else original
        if exact:
            rhs_identity = load(directory / "reviewed_rhs_identity.json")
            worker_modes = [item["fresh_mode_sha256"] for item in rhs_identity["records"]]
        else:
            worker_modes = [worker["delta"]["current_ordered_mode_sha256"] if required == "Q3_INTERFACE_CONTROL"
                            else worker["operator_identity"]["ordered_mode_sha256"]]
        checks = facts["checks"]
        settled_seconds = float(attempt.get("settled_seconds", np.nan))
        reserved_seconds = float(attempt.get("reserved_seconds", np.nan))
        settled_finite = bool(
            np.isfinite(settled_seconds) and settled_seconds >= 0.0
        )
        settled_within_reservation = bool(
            settled_finite
            and np.isfinite(reserved_seconds)
            and reserved_seconds >= 0.0
            and settled_seconds <= reserved_seconds
        )
        workflow_interval = parent.get("workflow_clock_interval", {})
        workflow_seconds = float(workflow_interval.get("budget_seconds", np.nan))
        workflow_time_gate = (
            v14_time_gate_facts(
                workflow_seconds, reserved_seconds, attempt_time_policy
            )
            if settled_finite
            and np.isfinite(reserved_seconds)
            and reserved_seconds > 0.0
            else None
        )
        checks.update({
            "batch": ledger["batch_identity"] == "review_v14",
            "time_policy_binding": len({
                attempt_time_policy,
                manifest_time_policy,
                parent_time_policy,
                watchdog_time_policy,
                worker_time_policy,
            }) == 1,
            "settled": bool(
                record["active_attempt"] is None
                and settled_finite
                and (
                    settled_within_reservation
                    or attempt_time_policy == V14_TIME_POLICY_OBSERVE_ONLY
                )
            ),
            "source": (len(source) == 40 and worker["source_sha"] == manifest["source_sha"] == source
                       == watchdog["source_state"]["source_sha"]),
            "source_clean_before_after": (
                watchdog["source_state"]["tracked_and_nonignored_untracked_clean"] is True
                and manifest["source_after"]["tracked_and_nonignored_untracked_clean"] is True
                and manifest["source_after"]["source_sha"] == source),
            "stage_profile": (worker["stage"] == manifest["solver"]["stage"] == resolved["solver"]["stage"] == required
                              and resolved["solver"]["preconditioner"] == SCHUR_PROFILE),
            "resolved_hash": facts["bindings"][str(resolved_path)] == manifest["resolved_config_sha256"],
            "input_hash": resolved["provenance"]["input_sha256"] == manifest["input_sha256"],
            "physical_mode": (manifest["physical_model_sha256"] == resolved["provenance"]["physical_model_sha256"] == expected_physical
                              and bool(worker_modes) and all(value == mode for value in worker_modes)),
            "parent_exit": (manifest["status"] == parent["status"] == "finished"
                            and parent["exit_status"] == watchdog["leader_exit_code"] == 0
                            and parent["result_classification"] == "worker_exit0"
                            and watchdog["classification"] == "COMPLETED"),
            "cleanup": watchdog["descendants_cleared"] is True and watchdog["remaining_child_pids"] == [],
            "zero_swap": (watchdog["sampled_process_tree_swap_peak_bytes"] == 0
                          and parent["job_swap_qualification"] == "qualified_zero"
                          and set(watchdog["global_swap_activity"]["delta"]) == {"pswpin_pages", "pswpout_pages"}
                          and all(value == 0 for value in watchdog["global_swap_activity"]["delta"].values())),
            "workflow_time": bool(
                workflow_time_gate is not None and workflow_time_gate["passed"]
            ),
        })
        facts["time_observations"] = {
            "settled_seconds": settled_seconds,
            "reserved_seconds": reserved_seconds,
            "settled_within_reservation": settled_within_reservation,
            "workflow": workflow_time_gate,
        }
        samples = 0
        trace_pass = True
        peak_rss = 0
        trace_path = directory / "watchdog/resources.jsonl"
        with trace_path.open(encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                samples += 1
                envelope = row["memory_envelope"]
                peak_rss = max(peak_rss, row["rss_bytes"])
                trace_pass &= bool(
                    row["all_status_readable"] is True and row["swap_bytes"] == 0
                    and 0 <= row["rss_bytes"] < min(row["launch_cap_bytes"], 8 << 30)
                    and envelope["effective_available_bytes"] >= envelope["reserve_bytes"]
                    and row["global_swap_pages"] == watchdog["global_swap_activity"]["baseline"])
        facts["bindings"][str(trace_path)] = _sha256_file(trace_path)
        checks["full_parent_samples"] = bool(samples and trace_pass
            and peak_rss == watchdog["sampled_process_tree_rss_peak_bytes"])
        worker_resources = _v14_resource_facts(SimpleNamespace(
            resources_path=directory / "v14_worker_resources.jsonl", workspace_cap=1 << 30,
            inventory_cap=(6 if exact else 3) << 30))
        facts["worker_resource_samples"] = worker_resources
        checks["inventory_workspace_samples"] = worker_resources["gate"]
        if not all(checks.values()):
            facts["reason"] = "predecessor_identity_or_parent_resource_failed"
            return facts

        if exact:
            rows = worker["solve_records"]
            stems = [row["stem"] for row in _Q1_Q2_RHS]
            checks["three_frozen_RHS_order"] = [row["stem"] for row in rows] == stems
            checks["RHS_identity"] = bool(
                rhs_identity["source_sha"] == source and rhs_identity["ordered_stems"] == stems
                and len(rhs_identity["records"]) == 3
                and all(item["fresh_physical_model_sha256"] == original
                        and bounded(item["fresh_A4y_relative_to_saved"], 1e-10)
                        for item in rhs_identity["records"]))
            for row in rows:
                native = row["augmented_residual"]
                rho = native["native_A4_norm"] / max(native["rhs_norm"], np.finfo(float).tiny)
                fields = row["field_metrics"]["fields"]
                checks[row["stem"]] = bool(bounded(rho, 1e-10)
                    and len(row["refinements"]) <= 2
                    and all(bounded(fields[name]["absolute_error_norm"] / max(fields[name]["reference_norm"], np.finfo(float).tiny), 1e-8)
                            for name in ("L2", "scaled_curl")))
            if required == "Q2_SCHUR_DIRECT":
                checks["post_release_recovery"] = bounded(worker["gates"]["post_release_recovery_relative"], 1e-10)
                checks["internal_factor_count"] = worker["lifecycle"]["internal_factor_count"] == 42
                checks["common_actions"] = all(bounded(worker["action_checks"][name], 1e-10) for name in (
                    "volume_explicit_vs_matrix_free", "volume_adjoint_explicit_vs_matrix_free",
                    "interface_explicit_vs_matrix_free", "physical_schur_vs_native_carrier",
                    "physical_schur_adjoint_formula", "local_backsolve_original_matrix_max_relative",
                    "g_minus_A4F_gamma_relative", "physical_schur_complex_inner_product_relative"))
        elif required == "Q3_INTERFACE_CONTROL":
            rows = worker["solve_records"]
            checks["three_frozen_RHS_order"] = [row["stem"] for row in rows] == [row["stem"] for row in _Q1_Q2_RHS]
            checks["internal_factor_count"] = worker["lifecycle"]["internal_factor_count"] == 42
            for row in rows:
                stem = row["stem"]
                feedback = stem.endswith("_02")
                residual = row["native_A4_residual_decomposition"]
                rho = residual["total_absolute_norm"] / max(residual["rhs_norm"], np.finfo(float).tiny)
                fields = row["field_metrics"]["fields"]
                errors = [fields[key]["absolute_error_norm"] / max(fields[key]["reference_norm"], np.finfo(float).tiny)
                          for key in ("L2", "scaled_curl")]
                fint_time_gate = v14_time_gate_facts(
                    row["elapsed_seconds"], 15.0, attempt_time_policy
                )
                checks[stem] = bool(
                    bounded(rho, .2 if feedback else .5)
                    and bounded(errors[0], .9 if feedback else .5)
                    and bounded(errors[1], .9 if feedback else .6)
                    and fint_time_gate["passed"]
                    and row["fint_apply_count_delta"] == 1
                    and _q3_interface_operation_audit(row["interface_facts"], 42)["passed"])
            balanced = worker["balanced_p6_audit"]
            closure = balanced["closure"]
            closure_ratio = closure["closure_norm"] / max(closure["operation_scale"], np.finfo(float).tiny)
            checks["BAL_H_closure"] = bounded(closure_ratio, 1e-8) and np.isfinite(closure["actual_defect_norm"])
            checks["BAL_H_work"] = bool(
                balanced["completed"] is True and bounded(balanced["q_bridge_relative"], 1e-10)
                and balanced["pc_counts"] == dict(C=2, smoother=1, A_structure=2, A_inner_true=0, PH_audit=0)
                and balanced["fint_apply_delta"] == 2 and balanced["h6_apply_delta"] == 1
                and balanced["native_A4_action_count"] == 2
                and len(balanced["coarse_calls"]) == 2
                and all(_q3_interface_operation_audit(call["interface_facts"], 42)["passed"]
                        for call in balanced["coarse_calls"]))
        else:
            checks.update(
                _v14_physical_checks(
                    worker["solver"],
                    worker["field"],
                    worker["comparison"],
                    time_policy=attempt_time_policy,
                )
            )
            checks["independent_final_A6"] = bounded(worker["final_explicit_relative_residual"], 1e-6)
            solve_clock_seconds = worker["gates"]["solve_clock_interval"]["budget_seconds"]
            solve_time_gate = v14_time_gate_facts(
                solve_clock_seconds, 10800.0, attempt_time_policy
            )
            checks["full_solve_clock"] = solve_time_gate["passed"]
            facts["time_observations"]["full_solve_clock"] = solve_time_gate
        facts["qualified"] = bool(all(checks.values()))
        facts["reason"] = "qualified" if facts["qualified"] else "predecessor_numerical_gate_failed"
    except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
        facts["reason"] = f"predecessor_evidence_error:{type(exc).__name__}:{exc}"
    return facts


def _v14_predecessor_gate(runtime, stage, *, resolved_payload=None) -> dict[str, Any]:
    required = {"Q4_ORIGINAL": "Q3_INTERFACE_CONTROL", "Q5_NOTCH": "Q4_ORIGINAL"}[stage]
    facts = _v14_settled_stage_gate(runtime, required)
    expected = ("9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f"
                if stage == "Q4_ORIGINAL" else
                "7a4d2a797a274fd4a02955647e91288908dd6a457c37984535fa2db9bfec06ec")
    current = (resolved_payload or {}).get("provenance", {}).get("physical_model_sha256")
    facts["checks"]["current_physical"] = current == expected
    facts["qualified"] = bool(facts["qualified"] and current == expected)
    if current != expected:
        facts["reason"] = "current_physical_identity_failed"
    return facts


def _q6_saved_q3_negative_evidence(
    *,
    stage_record: Mapping[str, Any],
    attempt: Mapping[str, Any],
    directory: Path,
    worker: Mapping[str, Any],
    manifest: Mapping[str, Any],
    watchdog: Mapping[str, Any],
    time_policy: str,
) -> dict[str, Any]:
    """Bind the three completed Q3 RHS calls without completing BAL_H."""

    packet_path = directory / "q3_rhs_packets" / "three_rhs_complete_before_balanced_audit.json"
    result = {
        "schema": "task039extra.v14.q6.saved-q3-negative.v1",
        "status": "EVIDENCE_INCOMPLETE",
        "measured_candidate_stop": False,
        "packet": {"path": str(packet_path)},
        "bindings": {},
        "values": [],
        "balanced_p6": {
            "status": "NOT_COMPLETED",
            "worker_error": worker.get("error"),
        },
    }
    expected_stems = [item["stem"] for item in _Q1_Q2_RHS]
    original_physical = "9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f"
    mode_sha = "dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2"

    try:
        packet_bytes = packet_path.read_bytes()
        packet = json.loads(packet_bytes)
        identity_path = directory / "reviewed_rhs_identity.json"
        identity_bytes = identity_path.read_bytes()
        identity = json.loads(identity_bytes)
        packet_sha = _sha256_bytes(packet_bytes)
        result["packet"]["sha256"] = packet_sha
        result["bindings"].update({
            str(packet_path): packet_sha,
            str(identity_path): _sha256_bytes(identity_bytes),
        })

        source = attempt["source_sha"]
        records = packet["solve_records"]
        identity_ok = (
            stage_record["active_attempt"] is None
            and np.isfinite(float(attempt["settled_seconds"]))
            and float(attempt["settled_seconds"]) >= 0.0
            and worker["source_sha"] == source
            and manifest["source_sha"] == source
            and manifest["source_after"]["source_sha"] == source
            and watchdog["source_state"]["source_sha"] == source
            and worker["stage"] == manifest["solver"]["stage"] == "Q3_INTERFACE_CONTROL"
            and manifest["physical_model_sha256"] == original_physical
            and manifest["source_after"]["tracked_and_nonignored_untracked_clean"] is True
            and watchdog["source_state"]["tracked_and_nonignored_untracked_clean"] is True
            and watchdog["descendants_cleared"] is True
            and watchdog["remaining_child_pids"] == []
            and worker["result_classification"] == "WORKER_FAILED"
            and worker["error"]["message"] == "Q3 p6 balanced input differs from the fresh native map"
            and "balanced_p6_audit" not in worker
            and packet["schema"] == "task039extra.v14.q3-three-rhs-complete.v1"
            and len(records) == len(_Q1_Q2_RHS)
            and [row["stem"] for row in records] == expected_stems
            and identity["source_sha"] == source
            and identity["ordered_stems"] == expected_stems
            and len(identity["records"]) == len(_Q1_Q2_RHS)
            and all(
                item["fresh_mode_sha256"] == mode_sha
                and item["fresh_physical_model_sha256"] == original_physical
                and np.isfinite(float(item["fresh_A4y_relative_to_saved"]))
                and float(item["fresh_A4y_relative_to_saved"]) >= 0.0
                and float(item["fresh_A4y_relative_to_saved"]) <= 1.0e-10
                for item in identity["records"]
            )
        )
        fint_deltas = []
        interface_apply_counts = []
        complete_rows = []
        for expected, row in zip(_Q1_Q2_RHS, records):
            packet_identity = row["packet"]["identity"]
            physical = packet_identity["reference_identity"]["physical"]
            identity_ok &= (
                all(
                    packet_identity[key] == expected[key]
                    for key in (
                        "stem", "logical_rhs", "input_sha256", "input_npz_sha256",
                        "g_sha256", "reference_json_sha256", "reference_npz_sha256",
                    )
                )
                and packet_identity["reference_identity"]["mode_sha256"] == mode_sha
                and physical["original_physical_sha256"] == original_physical
            )
            residual = row["native_A4_residual_decomposition"]
            fields = row["field_metrics"]["fields"]
            rhs_norm = float(residual["rhs_norm"])
            total_norm = float(residual["total_absolute_norm"])
            l2_abs = float(fields["L2"]["absolute_error_norm"])
            l2_ref = float(fields["L2"]["reference_norm"])
            curl_abs = float(fields["scaled_curl"]["absolute_error_norm"])
            curl_ref = float(fields["scaled_curl"]["reference_norm"])
            rho = total_norm / max(
                rhs_norm, np.finfo(float).tiny
            )
            eta = l2_abs / max(l2_ref, np.finfo(float).tiny)
            eta_curl = curl_abs / max(curl_ref, np.finfo(float).tiny)
            elapsed = float(row["elapsed_seconds"])
            fint_delta = row["fint_apply_count_delta"]
            operation_audit = _q3_interface_operation_audit(
                row["interface_facts"], 42
            )
            feedback = expected["stem"].endswith("_02")
            limits = (0.2, 0.9, 0.9) if feedback else (0.5, 0.5, 0.6)
            finite = all(np.isfinite(value) and value >= 0.0 for value in (
                rhs_norm, total_norm, l2_abs, l2_ref, curl_abs, curl_ref,
                rho, eta, eta_curl, elapsed,
            ))
            row_complete = bool(
                finite and rhs_norm > 0.0 and l2_ref > 0.0 and curl_ref > 0.0
                and fint_delta == 1 and operation_audit["passed"]
            )
            if not row_complete:
                raise ValueError(f"invalid saved Q3 evidence for {expected['stem']}")
            numeric_pass = bool(
                finite
                and rho <= limits[0]
                and eta <= limits[1]
                and eta_curl <= limits[2]
                and v14_time_gate_facts(elapsed, 15.0, time_policy)["passed"]
                and row_complete
            )
            result["values"].append({
                "stem": expected["stem"],
                "rho": rho,
                "eta": eta,
                "eta_curl": eta_curl,
                "elapsed_seconds": elapsed,
                "operation_audit": operation_audit,
                "numeric_pass": numeric_pass,
            })
            fint_deltas.append(fint_delta)
            interface_apply_counts.append(
                row["interface_facts"].get("apply_count")
            )
            complete_rows.append(row_complete)

        identity_ok &= (
            fint_deltas == [1, 1, 1]
            and interface_apply_counts == [1, 2, 3]
            and packet["three_rhs_fint_apply_deltas"] == fint_deltas
            and packet["three_rhs_fint_apply_count"] == 3
            and all(complete_rows)
        )
        rejected = any(not value["numeric_pass"] for value in result["values"])
        if identity_ok and len(result["values"]) == 3 and rejected:
            result.update(
                status="MEASURED_NEGATIVE_CANDIDATE",
                measured_candidate_stop=True,
                reason="three_frozen_rhs_recomputed_admission_failed_before_balanced_audit",
            )
        else:
            result["reason"] = "saved_q3_negative_evidence_incomplete"
    except (OSError, ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["reason"] = "saved_q3_negative_evidence_incomplete"
    return result


def _v14_history_facts(
    root: Path,
    common: Mapping[str, Any],
    solver_facts: Mapping[str, Any],
    *,
    notch: bool,
    physical_sha256: str,
) -> dict[str, Any]:
    """Compare hash-bound measured nodes, including the nearest actual times."""

    path = root / "benchmarks/artifacts/task39extra/p4_schur_v14/root_engineering/frozen_history.json"
    facts = {
        "path": str(path), "status": "MISSING",
        "new_PDE_runs": 0, "new_operator_actions": 0,
        "comparison_rule": "same iteration and nearest measured conservative time; no interpolation",
        "current_time_scope": "conservative solve time including checkpoint evaluation",
        "diagnostic_frequency_note": "V14 native residual every 8, field every 32; historical recorded cadence retained",
        "same_identity_cases": [],
    }
    if not path.is_file():
        return facts

    def node_values(row, *, v12=False):
        return {
            "iteration": int(row["iteration"]),
            "explicit_true_residual": float(row["true_residual"] if v12 else row["explicit_true_residual"]),
            "solve_seconds": float(row["elapsed_seconds_conservative"] if v12 else row["solve_seconds"]),
            "monotonic_seconds": row.get("elapsed_seconds_monotonic") if v12 else None,
            "reference_field": row.get("reference_field"),
            "cost": row.get("cost"),
        }

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        facts["sha256"] = _sha256_file(path)
        current = {int(row["iteration"]): node_values(row)
                   for row in solver_facts["snapshots"]}
        current_32_64 = {str(i): current[i] for i in (32, 64) if i in current}
        terminal = int(solver_facts["iterations"])
        targets = sorted({i for i in (32, 64, terminal) if i in current and i > 0})
        facts["current_nodes_32_64"] = current_32_64
        early_terminal = terminal < 64 and float(solver_facts["final_true_residual"]) <= 1e-6
        facts["required_nodes_gate"] = {
            "early_terminal_before_64": early_terminal,
            "current_32_present": 32 in current, "current_64_present": 64 in current,
            "passed": bool(notch or early_terminal or (32 in current and 64 in current)),
            "scope": "availability only; never a reason to extend a stopped solve",
        }
        mode = str(common["fine"]["mode_sha256"])
        for case in payload["cases"]:
            v12 = "source_record" in case
            old_mode = case["operator_identity"]["mode_sha256"] if v12 else case["mode_sha256"]
            if case["physical_model_sha256"] != physical_sha256 or old_mode != mode:
                continue
            binding = case["source_record"] if v12 else case["raw_binding"]
            source_path = root / binding["path"]
            if _sha256_file(source_path) != binding["sha256"]:
                raise ValueError(f"historical raw binding changed: {source_path}")
            if v12:
                source = json.loads(source_path.read_text(encoding="utf-8"))
                raw_nodes = source["candidates"][0]["node_records"]
            else:
                with source_path.open(encoding="utf-8") as stream:
                    raw_nodes = [json.loads(line) for line in stream if line.strip()]
            nodes = {}
            for raw in raw_nodes:
                node = node_values(raw, v12=v12)
                if not np.isfinite(node["solve_seconds"]) or not np.isfinite(node["explicit_true_residual"]):
                    raise ValueError("non-finite historical residual or time")
                nodes.setdefault(node["iteration"], node)
            if not nodes:
                raise ValueError("historical binding contains no measured nodes")
            nearest = []
            for i in targets:
                target = current[i]
                old = min(nodes.values(), key=lambda x: (abs(x["solve_seconds"] - target["solve_seconds"]), x["iteration"]))
                nearest.append({
                    "current": target, "historical": old,
                    "signed_time_difference_seconds": old["solve_seconds"] - target["solve_seconds"],
                    "requested_time_inside_measured_range": min(x["solve_seconds"] for x in nodes.values()) <= target["solve_seconds"] <= max(x["solve_seconds"] for x in nodes.values()),
                })
            facts["same_identity_cases"].append({
                "label": case["label"], "source_sha": case["source_sha"],
                "raw_binding": dict(binding),
                "required_32_64_nodes": {str(i): nodes[i] for i in (32, 64) if i in nodes},
                "nearest_time_nodes": nearest,
                "node_time_scope": case.get("node_time_scope", "V12 elapsed_seconds_conservative; monotonic reported separately"),
                "measured_iteration_cadence": sorted(nodes),
                "setup_to_solve_start": case.get("setup_to_solve_start"),
                "stage_times": case.get("stage_times"),
                "resource": case.get("resource"),
                "scope": case.get("scope"),
            })
        facts["status"] = "AVAILABLE" if facts["same_identity_cases"] else "NO_MATCHING_HISTORY"
    except (OSError, ValueError, TypeError, KeyError) as exc:
        facts.update(status="READ_ERROR", error=f"{type(exc).__name__}: {exc}")
    return facts


def _v14_resource_facts(runtime: _V14Runtime) -> dict[str, Any]:
    """Stream worker-emitted parent-tree samples without retaining the log."""

    path = Path(runtime.resources_path)
    require_zero_swap = bool(getattr(runtime, "require_zero_swap", True))
    facts = {
        "path": str(path), "status": "MISSING", "sample_count": 0,
        "scope": "worker-emitted samples of the parent process tree through this call",
        "final_parent_cleanup_included": False,
        "final_authority": "settled parent run_summary and watchdog/summary.json",
        "swap_gate_enforced": require_zero_swap,
        "zero_swap": True, "all_status_readable": True, "pss_all_readable": True,
        "rss_peak_bytes": None, "pss_peak_bytes": None, "swap_peak_bytes": None,
        "ledger_inventory_peak_bytes": 0, "ledger_workspace_peak_bytes": 0,
        "first_failed_sample": None, "gate": False,
    }
    if not path.is_file():
        facts.update(zero_swap=False, all_status_readable=False, pss_all_readable=False)
        return facts
    line_number = 0
    try:
        with path.open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                row = json.loads(line)
                facts["sample_count"] += 1
                rss, swap = int(row["rss_bytes"]), int(row["swap_bytes"])
                envelope = row["memory_envelope"]
                cap = row["inventory_memory_cap_bytes"]
                frozen_cap = getattr(runtime, "inventory_cap", None)
                if frozen_cap is not None:
                    cap = int(frozen_cap) if cap is None else min(int(cap), int(frozen_cap))
                rss_limit = (
                    int(row["launch_cap_bytes"])
                    if getattr(runtime, "physical_memory_pressure", False)
                    else min(int(row["launch_cap_bytes"]), 8 << 30)
                )
                workspace_value = int(row["workspace_live_bytes"])
                workspace_cap = getattr(runtime, "workspace_cap", None)
                checks = {
                    "readable": row["all_status_readable"] is True,
                    "zero_swap": swap == 0,
                    "rss": 0 <= rss < rss_limit,
                    "reserve": int(envelope["effective_available_bytes"]) >= int(envelope["reserve_bytes"]),
                    "inventory": 0 <= int(row["inventory_used_bytes"]) and (cap is None or int(row["inventory_used_bytes"]) <= int(cap)),
                    "workspace": 0 <= workspace_value and (
                        workspace_cap is None or workspace_value <= workspace_cap
                    ),
                }
                gate_checks = dict(checks)
                gate_checks["zero_swap"] = (
                    checks["zero_swap"] or not require_zero_swap
                )
                facts["zero_swap"] &= checks["zero_swap"]
                facts["all_status_readable"] &= checks["readable"]
                for name, value in (("rss_peak_bytes", rss), ("swap_peak_bytes", swap)):
                    facts[name] = value if facts[name] is None else max(facts[name], value)
                pss = row.get("pss_bytes")
                readable_pss = row.get("pss_all_readable") is True and pss is not None
                facts["pss_all_readable"] &= readable_pss
                if readable_pss:
                    facts["pss_peak_bytes"] = max(facts["pss_peak_bytes"] or 0, int(pss))
                facts["ledger_inventory_peak_bytes"] = max(facts["ledger_inventory_peak_bytes"], int(row["inventory_peak_bytes"]))
                facts["ledger_workspace_peak_bytes"] = max(facts["ledger_workspace_peak_bytes"], int(row["workspace_peak_bytes"]))
                facts["last_timestamp_ns"] = row["timestamp_ns"]
                if not all(gate_checks.values()) and facts["first_failed_sample"] is None:
                    facts["first_failed_sample"] = {"line": line_number, "label": row["label"], "checks": gate_checks}
        facts["sha256"] = _sha256_file(path)
        facts["status"] = "AVAILABLE" if facts["sample_count"] else "EMPTY"
        facts["gate"] = bool(facts["sample_count"] and facts["first_failed_sample"] is None)
        if not facts["sample_count"]:
            facts.update(zero_swap=False, all_status_readable=False, pss_all_readable=False)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        facts.update(status="READ_ERROR", gate=False, failed_line=line_number,
                     error=f"{type(exc).__name__}: {exc}")
    return facts



def _v14_operator_identity(
    common: Mapping[str, Any],
    resolved_payload: Mapping[str, Any],
    partition: Any,
    *,
    stage: str,
) -> tuple[dict[str, Any], str]:
    from src.runners.physical_macro_controls import _mapping_identity_sha256
    from src.solvers.condensed_fine_reference import native_map_arrays

    provenance = resolved_payload.get("provenance", {})
    if not isinstance(provenance, Mapping):
        provenance = {}
    input_sha = str(
        provenance.get("input_sha256", resolved_payload.get("input_sha256", ""))
    )
    physical_sha = str(
        provenance.get(
            "physical_model_sha256",
            resolved_payload.get("physical_model_sha256", ""),
        )
    )
    if len(input_sha) != 64 or len(physical_sha) != 64:
        raise ValueError("V14 fresh p6 stage requires input and physical identities")
    p4_map = native_map_arrays(
        common["levels"]["spaces"][4], common["levels"]["floquets"][4]
    )
    p6_map = native_map_arrays(
        common["levels"]["spaces"][6], common["levels"]["floquets"][6]
    )
    identity = {
        "schema": "task039extra.v14.fresh-p6-operator-identity.v1",
        "stage": str(stage),
        "input_sha256": input_sha,
        "physical_model_sha256": physical_sha,
        "ordered_mode_sha256": str(common["fine"]["mode_sha256"]),
        "p4_native_map_sha256": _mapping_identity_sha256(p4_map),
        "p6_native_map_sha256": _mapping_identity_sha256(p6_map),
        "p4_storage_rows": int(common["p4"]["dtn_action"].carrier.global_rows),
        "p6_storage_rows": int(common["fine"]["dtn_action"].carrier.global_rows),
        "partition": {
            "storage_size": int(partition.storage_size),
            "active_rows": int(partition.active_rows),
            "gamma_rows": int(partition.gamma_rows),
            "active_full_indices_sha256": _sha256_bytes(
                np.asarray(partition.active_full_indices, dtype=np.int64).tobytes()
            ),
            "gamma_full_indices_sha256": _sha256_bytes(
                np.asarray(partition.gamma_full_indices, dtype=np.int64).tobytes()
            ),
        },
        "quadrature": _jsonable(common["quadrature"]),
        "native_aq_projection_check": _jsonable(
            common.get("native_aq_projection_check")
        ),
        "reference_used_for_operator_or_initial_guess": False,
        "initial_guess": "zero",
    }
    encoded = json.dumps(
        _jsonable(identity), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return identity, _sha256_bytes(encoded)


def _v14_p6_field_comparison(
    common: Mapping[str, Any], solution: Any, reference: np.ndarray | None
) -> dict[str, Any]:
    """Compare the fresh p6 field with the bound reference in the metric space."""

    if reference is None:
        raise ValueError("reference field vector is unavailable")
    solution_array = np.asarray(solution.array, dtype=np.complex128)
    reference_array = np.asarray(reference, dtype=np.complex128)
    if solution_array.shape != reference_array.shape:
        raise ValueError(
            "fresh p6 solution and reference field have different storage shapes"
        )
    metric = common["metric"]
    indices = np.asarray(metric.mass.indices, dtype=np.int64)
    from src.solvers.physical_error_diagnostics import metric_square

    error = solution_array[indices] - reference_array[indices]
    reference_values = reference_array[indices]
    fields: dict[str, dict[str, float]] = {}
    for name, action in (("L2", metric.mass), ("scaled_curl", metric.curl)):
        error_norm = float(np.sqrt(metric_square(action, error)))
        reference_norm = float(np.sqrt(metric_square(action, reference_values)))
        fields[name] = {
            "absolute_error_norm": error_norm,
            "reference_norm": reference_norm,
            "relative": error_norm / max(reference_norm, np.finfo(float).tiny),
        }
    return fields


def _run_v20_release_after_final_residual(
    runtime: _V14Runtime,
    common: dict[str, Any],
    stack: Mapping[str, Any],
    outer_adapter: Any,
    *,
    stage: str,
    prefix: str,
    identity: Mapping[str, Any],
    solve_result: Mapping[str, Any],
    final_solution: Any,
    rhs: Any,
    rhs_norm: float,
    final_explicit_relative: float,
    release_after_final_residual: bool,
) -> dict[str, Any] | None:
    """Run the exact V20 save/gate/release/post-native boundary sequence."""

    if not release_after_final_residual:
        return None
    release_gate_facts = {
        "field_packet_saved": bool(
            getattr(outer_adapter, "_final_packet_saved", False)
        ),
        "pre_release_A6_relative": final_explicit_relative,
        "pre_release_A6_limit": 1.0e-6,
        "pre_release_A6_finite": bool(np.isfinite(final_explicit_relative)),
        "pre_release_A6_passed": bool(
            np.isfinite(final_explicit_relative)
            and final_explicit_relative <= 1.0e-6
        ),
        "identity_values": {
            key: float(solve_result["final_evaluation"][key])
            for key in (
                "port_closure_relative",
                "internal_residual_relative",
                "native_identity_relative",
                "schur_port_identity_relative",
            )
        },
        "identity_limits": {
            "port_closure_relative": 1.0e-8,
            "internal_residual_relative": 1.0e-10,
            "native_identity_relative": 1.0e-10,
            "schur_port_identity_relative": 1.0e-10,
        },
    }
    release_gate_facts["pre_release_identity_passed"] = all(
        np.isfinite(value)
        and value <= release_gate_facts["identity_limits"][key]
        for key, value in release_gate_facts["identity_values"].items()
    )
    release_gate_facts["passed"] = bool(
        release_gate_facts["field_packet_saved"]
        and release_gate_facts["pre_release_A6_passed"]
        and release_gate_facts["pre_release_identity_passed"]
    )
    runtime.marker("v20_release_gate_checked", release_gate_facts)
    if not release_gate_facts["passed"]:
        release_gate_facts["classification"] = "V20_RELEASE_GATE_FAIL"
        release_gate_facts["reason"] = (
            "finite-but-over-limit residual/identity"
            if release_gate_facts["pre_release_A6_finite"]
            else "nonfinite pre-release A6"
        )
        _save_packet(
            runtime.directory / "release_gate_failure",
            "v20_release_gate",
            release_gate_facts,
            runtime=runtime,
        )
        runtime.marker("v20_release_gate_failed", release_gate_facts)
        raise V20ReleaseGateStop(release_gate_facts)

    runtime.marker(
        "v20_preconditioner_release_started",
        {"pre_release_gate_passed": True},
    )
    deferred_cleanup = getattr(runtime, "_deferred_balanced_cleanup", None)
    if deferred_cleanup is None:
        raise RuntimeError(
            "V20 expected the BAL_H/H6 cleanup to remain deferred until after A6"
        )
    deferred_cleanup()
    runtime.marker(
        "v20_preconditioner_release_complete",
        {"h6_and_bal_h_released_after_final_A6": True},
    )
    p6_release = outer_adapter.release_after_final_residual()
    p4_release = stack.get("release_after_final_residual")
    if not callable(p4_release):
        raise RuntimeError("V20 stack did not expose its post-KSP release hook")
    p4_release = p4_release()
    release_facts = {
        "p6": p6_release,
        "p4": p4_release,
        "h6_and_bal_h": "RELEASED",
        "matrix_lifecycle_policy": "MATRIX_RETAINED_BACKEND_DEPENDENCY",
    }
    post_release_applied = rhs.duplicate()
    post_release_residual = None
    try:
        common["fine"]["physical_action"].apply(
            final_solution, post_release_applied
        )
        post_release_residual = rhs.copy()
        post_release_residual.axpy(-1.0, post_release_applied)
        post_release_relative = float(post_release_residual.norm()) / rhs_norm
        if not np.isfinite(post_release_relative):
            raise FloatingPointError(
                f"{stage} post-release A6 residual is nonfinite"
            )
        post_release_residual_packet = _save_packet(
            runtime.directory / "post_release_final_residual",
            f"{prefix}_post_release_final",
            {
                "schema": "task039extra.v20.post-release-final-residual-packet.v1",
                "identity": identity,
                "rhs_norm": rhs_norm,
                "independent_action_count": 1,
                "explicit_relative_residual": post_release_relative,
                "release_facts": release_facts,
                "rhs": np.asarray(rhs.array).copy(),
                "solution": np.asarray(final_solution.array).copy(),
                "applied": np.asarray(post_release_applied.array).copy(),
                "residual": np.asarray(post_release_residual.array).copy(),
            },
            runtime=runtime,
        )
        runtime.marker(
            "v20_post_release_final_residual_complete",
            {
                "packet": post_release_residual_packet,
                "relative": post_release_relative,
                "release_complete": True,
            },
        )
    except BaseException:
        if post_release_residual is not None:
            post_release_residual.destroy()
        post_release_applied.destroy()
        raise
    return {
        "release_gate": release_gate_facts,
        "release_facts": release_facts,
        "post_release_applied": post_release_applied,
        "post_release_residual": post_release_residual,
        "post_release_relative": post_release_relative,
        "post_release_residual_packet": post_release_residual_packet,
    }


def _p4_repair_enabled(policy) -> bool:
    if policy is None:
        return False
    if isinstance(policy, Mapping):
        return bool(policy.get("enabled", False))
    return bool(getattr(policy, "enabled", False))


def _pc_count_facts(pc, stack, positive, repair_policy):
    facts = {
        "bal_h": int(pc.apply_count),
        "p4_mat_solve": int(stack["inverse"].solve_count),
        "h6": int(positive["h6"].apply_count),
    }
    if _p4_repair_enabled(repair_policy):
        facts.update(
            {
                # ``coarse_calls`` is intentionally reset for every PC
                # application.  The cumulative counter is incremented only
                # after the native A4 gate and is therefore the source of
                # truth for a later X2/reporting query.
                "p4_logical_apply_count": int(
                    pc.successful_logical_apply_count
                ),
                "p4_recent_logical_apply_count": int(len(pc.coarse_calls)),
                "p4_call_records": [dict(record) for record in pc.coarse_calls],
            }
        )
    return facts


def _v14_q4_q5_fullspace(
    runtime: _V14Runtime,
    common: dict[str, Any],
    resolved_payload: Mapping[str, Any],
    *,
    stage: str,
    predecessor: Mapping[str, Any],
    stack_factory: Any | None = None,
    outer_adapter_factory: Any | None = None,
    release_after_final_residual: bool = False,
    official_jit_options: Mapping[str, Any] | None = None,
    reference_mode: str = "required",
    notch_override: bool | None = None,
    p4_repair_policy=None,
    p4_repair_vector_sink=None,
    p4_repair_vector_capture=None,
    p4_logical_apply_hook=None,
    p4_stack_ready_hook=None,
    pc_fine_action_factory=None,
    packed_power10=False,
    sum_factorized_work=False,
    sum_factorized_power10=None,
    direct_selected_backend=False,
    reuse_projection_work=False,
    formal_release_timing=False,
) -> dict[str, Any]:
    """Run one fresh p6 outer solve with the live interface BAL_H stack.

    The p4 stack is rebuilt inside this function for both conditional stages.
    Only structural identity is shared by the implementation; numeric factors,
    local directions and the p6 positive setup are constructed afresh for each
    stage.  The existing reference is loaded lazily by the checkpoint
    evaluation closure and is never handed to an operator, preconditioner, or
    initial guess; official output remains gated by the independent final
    residual.
    """

    from src.runners.physical_macro_v12 import (
        _compare_saved_output,
        _load_reference_binding,
        _write_checkpoint,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        build_physical_rhs,
        recover_p0_outputs,
    )
    from src.solvers.physical_balanced_fgmres import run_balanced_fgmres
    from src.io.physical_intermediate_profile import COARSE_DEGREE_SPEED_PROFILE
    from .workflow_timebase import (
        CONSERVATIVE_REALTIME,
        ClockBudget,
        checked_interval,
        clock_sample,
    )

    stage = str(stage)
    v25_coarse_stage = (
        str(resolved_payload.get("solver", {}).get("preconditioner", ""))
        == COARSE_DEGREE_SPEED_PROFILE
    )
    if stage not in {
        "Q4_ORIGINAL", "Q3_ORIGINAL", "Q2_ORIGINAL", "Q5_NOTCH",
        "U4_ORIGINAL", "U5_NOTCH",
        "U4_EXACT_FALLBACK", "X2_ORIGINAL", "Y3_ORIGINAL",
        "Z2_NOTCH_H10", "Z3_ORIGINAL_H7P5", "Z4_NOTCH_H7P5",
    }:
        raise ValueError(f"unsupported fresh p6 stage {stage!r}")
    retained_stage = stage in {
        "X2_ORIGINAL", "Y3_ORIGINAL",
        "Z2_NOTCH_H10", "Z3_ORIGINAL_H7P5", "Z4_NOTCH_H7P5",
    } or (v25_coarse_stage and stage in {"Q4_ORIGINAL", "Q3_ORIGINAL", "Q2_ORIGINAL"})
    if retained_stage != (outer_adapter_factory is not None):
        raise ValueError("only retained-space original stages use the outer adapter")
    release_stages = {
        "Y3_ORIGINAL", "Z2_NOTCH_H10", "Z3_ORIGINAL_H7P5", "Z4_NOTCH_H7P5"
    }
    if v25_coarse_stage:
        release_stages.update({"Q4_ORIGINAL", "Q3_ORIGINAL", "Q2_ORIGINAL"})
    if release_after_final_residual and stage not in release_stages:
        raise ValueError("post-KSP release is not enabled for this stage")
    if reference_mode not in {"required", "authority_limited"}:
        raise ValueError(f"unsupported reference mode {reference_mode!r}")
    if stage == "Z2_NOTCH_H10" and reference_mode != "required":
        raise ValueError("Z2_NOTCH_H10 must use the matched-reference branch")
    if (
        v25_coarse_stage and stage in {"Q4_ORIGINAL", "Q3_ORIGINAL", "Q2_ORIGINAL"}
    ) or stage in {"Z3_ORIGINAL_H7P5", "Z4_NOTCH_H7P5"}:
        if reference_mode != "authority_limited":
            raise ValueError(f"{stage} must use the authority-limited branch")
    authority_limited_stages = {"Z3_ORIGINAL_H7P5", "Z4_NOTCH_H7P5"}
    if v25_coarse_stage:
        authority_limited_stages.update({"Q4_ORIGINAL", "Q3_ORIGINAL", "Q2_ORIGINAL"})
    if reference_mode == "authority_limited" and stage not in authority_limited_stages:
        raise ValueError("authority-limited reference mode is reserved for V21 Z3/Z4")
    notch = (
        bool(notch_override)
        if notch_override is not None
        else stage in {"Q5_NOTCH", "U5_NOTCH"}
    )
    expected_notch = "positive_x_middle_y_z40_80"
    cell_notch = getattr(common["cfg"], "cell_notch", None)
    if notch and cell_notch != expected_notch:
        raise ValueError(f"{stage} received the wrong frozen notch recipe")
    if not notch and cell_notch not in (None, ""):
        raise ValueError(f"{stage} must use the original, unnotched geometry")

    resources = runtime.contract["resources"]
    time_policy = normalize_v14_time_policy(getattr(runtime, "time_policy", None))
    time_policy_facts = v14_time_policy_facts(time_policy)
    stage_budget = resources.get("stage_budgets", {}).get(stage)
    if not isinstance(stage_budget, Mapping):
        raise ValueError(f"{stage} has no frozen stage budget")
    solve_limit = float(stage_budget["solve_seconds"])
    workflow_limit = min(
        float(stage_budget["workflow_seconds"]),
        float(getattr(runtime, "workflow_reserved_seconds", 0.0)),
    )
    if (
        workflow_limit <= 0.0
        or (
            not v25_coarse_stage
            and stage in {"Q4_ORIGINAL", "Q5_NOTCH"}
            and solve_limit != 10800.0
        )
        or (
            stage in {
                "U4_ORIGINAL", "U5_NOTCH", "U4_EXACT_FALLBACK", "X2_ORIGINAL",
                "Z2_NOTCH_H10", "Z3_ORIGINAL_H7P5", "Z4_NOTCH_H7P5",
            }
            and solve_limit <= 0.0
        )
    ):
        raise ValueError(f"{stage} has an invalid conditional-stage budget")

    provenance = resolved_payload.get("provenance", {})
    if not isinstance(provenance, Mapping):
        provenance = {}
    input_sha = str(provenance.get("input_sha256", ""))
    physical_sha = str(provenance.get("physical_model_sha256", ""))
    if len(input_sha) != 64 or len(physical_sha) != 64:
        raise ValueError(f"{stage} requires hash-bound input and physical identities")

    prefix = (
        "y3" if stage == "Y3_ORIGINAL" else
        "x2" if stage == "X2_ORIGINAL" else
        "z2" if stage == "Z2_NOTCH_H10" else
        "z3" if stage == "Z3_ORIGINAL_H7P5" else
        "z4" if stage == "Z4_NOTCH_H7P5" else
        "u5" if stage == "U5_NOTCH" else
        "u4_fallback" if stage == "U4_EXACT_FALLBACK" else
        "u4" if stage == "U4_ORIGINAL" else
        "q5" if notch else f"q{int(common.get('coarse_degree', 4))}"
    )
    final_solution = rhs = final_applied = final_residual = None
    post_release_applied = post_release_residual = None
    post_release_residual_packet = None
    post_release_relative = None
    release_facts: dict[str, Any] | None = None
    release_timing_facts: dict[str, Any] | None = None
    solve_result: dict[str, Any] | None = None
    solve_clock: ClockBudget | None = None
    checkpoint_records: list[dict[str, Any]] = []
    pc_boundary_records: list[dict[str, Any]] = []
    stop_state: dict[str, Any] = {
        "requested": False,
        "reason": None,
        **time_policy_facts,
    }
    reference_binding: dict[str, Any] | None = None
    reference_vector: np.ndarray | None = None
    reference_attempted = False
    reference_error: dict[str, Any] | None = None
    reference_load_workspace_label = f"{prefix}_reference_load"
    reference_load_workspace_live = False
    reference_load_workspace_bytes = 64 << 20
    reference_workspace_label = f"{prefix}_reference_evaluation"
    reference_workspace_live = False
    reference_workspace_bytes = 0
    reference_field_temp_bytes = 0
    field_checkpoint_records: list[dict[str, Any]] = []
    outer_active = False
    outer_workspace_label = f"{prefix}_outer_krylov"
    outer_workspace_live = False
    outer_workspace_bytes = 0
    outer_adapter = None
    lifecycle_boundaries: dict[str, dict[str, Any]] = {}

    def lifecycle_boundary(
        name: str,
        *,
        clock_override: Mapping[str, Any] | None = None,
        **facts: Any,
    ) -> dict[str, Any]:
        sample = dict(clock_sample() if clock_override is None else clock_override)
        lifecycle_boundaries[name] = dict(sample)
        runtime.marker(
            f"{prefix}_{name}",
            {"clock": sample, **facts},
        )
        return sample

    def attach_lifecycle(record: dict[str, Any]) -> dict[str, Any]:
        lifecycle = record.setdefault("lifecycle", {})
        lifecycle["boundaries"] = {
            key: dict(value) for key, value in lifecycle_boundaries.items()
        }
        pairs = {
            "setup": ("setup_started", "setup_end"),
            "outer_adapter": (
                "outer_adapter_started",
                "outer_adapter_ended",
            ),
            "final_native_check": (
                "final_native_check_started",
                "final_native_check_ended",
            ),
            "release_check": ("release_check_started", "release_check_ended"),
            "official_postprocess": (
                "official_postprocess_started",
                "official_postprocess_ended",
            ),
        }
        lifecycle["intervals"] = {}
        for name, (start_name, end_name) in pairs.items():
            start = lifecycle_boundaries.get(start_name)
            end = lifecycle_boundaries.get(end_name)
            if start is not None and end is not None:
                interval = checked_interval(
                    start,
                    end,
                    policy=CONSERVATIVE_REALTIME,
                )
                interval["monotonic_seconds"] = float(
                    interval["elapsed_seconds"]["monotonic"]
                )
                lifecycle["intervals"][name] = interval
        return record

    lifecycle_boundary(
        "setup_started",
        clock_override=getattr(runtime, "workflow_clock_start", None),
        stage=stage,
        includes="entire worker workflow from parent workflow clock start",
    )

    if release_after_final_residual:
        runtime._defer_balanced_release = True
        runtime._deferred_balanced_cleanup = None

    @contextmanager
    def owned_p6_vectors():
        nonlocal outer_active, outer_workspace_live
        nonlocal reference_load_workspace_live, reference_workspace_live
        nonlocal reference_vector
        try:
            yield
        finally:
            if outer_active:
                try:
                    runtime.finish_outer_solve()
                finally:
                    outer_active = False
            if outer_workspace_live:
                runtime.release_workspace(outer_workspace_label)
                outer_workspace_live = False
            if reference_load_workspace_live:
                runtime.release_workspace(reference_load_workspace_label)
                reference_load_workspace_live = False
            if reference_workspace_live:
                runtime.release_workspace(reference_workspace_label)
                reference_workspace_live = False
            if reference_binding is not None:
                reference_binding.pop("x_ref", None)
            reference_vector = None
            if final_residual is not None:
                final_residual.destroy()
            if final_applied is not None:
                final_applied.destroy()
            if post_release_residual is not None:
                post_release_residual.destroy()
            if post_release_applied is not None:
                post_release_applied.destroy()
            if final_solution is not None:
                final_solution.destroy()
            if outer_adapter is not None:
                outer_adapter.destroy()
            deferred_cleanup = getattr(runtime, "_deferred_balanced_cleanup", None)
            if deferred_cleanup is not None:
                deferred_cleanup()
            runtime._defer_balanced_release = False
            if rhs is not None:
                rhs.destroy()

    def append(name: str, row: Mapping[str, Any]) -> None:
        _append_jsonl(runtime.directory / str(name), row)

    def current_workflow_interval() -> dict[str, Any]:
        return dict(runtime.workflow_clock_interval())

    def apply_fine(source: Any) -> Any:
        """Return an owned A6 action output for the generic Krylov adapter."""

        target = source.duplicate()
        try:
            common["fine"]["physical_action"].apply(source, target)
        except BaseException:
            target.destroy()
            raise
        return target

    def evaluation_reference() -> np.ndarray:
        """Load the immutable reference once, for checkpoint diagnostics only."""

        nonlocal reference_attempted, reference_binding, reference_vector
        nonlocal reference_error, reference_load_workspace_live
        nonlocal reference_workspace_live, reference_workspace_bytes
        nonlocal reference_field_temp_bytes
        if reference_attempted:
            if reference_error is not None:
                raise ValueError(reference_error["message"])
            if reference_vector is None:
                raise ValueError("reference evaluation vector is unavailable")
            return reference_vector

        reference_attempted = True
        try:
            runtime.reserve_workspace(
                reference_load_workspace_label,
                reference_load_workspace_bytes,
            )
            reference_load_workspace_live = True
            runtime.marker(
                f"{prefix}_reference_loading_started",
                {
                    "workspace_bytes": reference_load_workspace_bytes,
                    "fixed_storage_rows": 173802,
                    "complex_scalar_bytes": np.dtype(np.complex128).itemsize,
                    "scope": (
                        "bounded reference packet/load and field-diagnostic pool; "
                        "not an operator or initial-guess allocation"
                    ),
                },
            )
            binding = _load_reference_binding(
                runtime.root
                / "benchmarks/artifacts/task39extra/v6_recursive/g0_inventory.json",
                notch=notch,
            )
            reference_model = binding.get("model", {})
            if reference_model.get("physical_sha") != physical_sha:
                raise ValueError(f"{stage} reference physical identity differs")
            if reference_model.get("mode_sha") != identity["ordered_mode_sha256"]:
                raise ValueError(f"{stage} reference ordered mode identity differs")
            if stage == "Z2_NOTCH_H10":
                # The historical loader binds only the reference model/mode
                # hashes.  Z2 additionally compares the live numeric MPC map
                # and the saved independent physical RHS; no ABI or reference
                # is re-qualified here.
                from src.solvers.condensed_fine_reference import (
                    native_map_arrays,
                    project_unconstrained_mpc_dual,
                )
                from src.solvers.physical_map_identity import (
                    compare_native_map_identity,
                )

                native_map_manifest_path = Path(
                    str(binding["reference_native_map"])
                )
                native_map_manifest = json.loads(
                    native_map_manifest_path.read_text(encoding="utf-8")
                )
                native_map_archive_path = Path(
                    str(native_map_manifest["arrays"]["path"])
                )
                native_map_archive_bytes = native_map_archive_path.read_bytes()
                if _sha256_bytes(native_map_archive_bytes) != native_map_manifest[
                    "arrays"
                ]["sha256"]:
                    raise ValueError("Z2 reference native-map archive hash changed")
                with np.load(native_map_archive_path, allow_pickle=False) as archive:
                    saved_native_map = {
                        key: np.asarray(archive[descriptor["array_key"]])
                        for key, descriptor in native_map_manifest.items()
                        if key
                        in {
                            "dofmap",
                            "geometry",
                            "geometry_dofmap",
                            "permutations",
                            "slaves",
                            "masters",
                            "coefficients",
                            "offsets",
                            "independent_indices",
                        }
                    }
                current_native_map = native_map_arrays(
                    common["levels"]["spaces"][6],
                    common["levels"]["floquets"][6],
                )
                native_map_facts = compare_native_map_identity(
                    current_native_map,
                    saved_native_map,
                    context="Z2 matched notch reference native map",
                )

                rhs_manifest_path = native_map_manifest_path.parent / (
                    "reference_pre_numeric_rhs.json"
                )
                rhs_manifest_bytes = rhs_manifest_path.read_bytes()
                if _sha256_bytes(rhs_manifest_bytes) != _V21_REFERENCE_PRE_NUMERIC_RHS_JSON_SHA256:
                    raise ValueError("Z2 reference pre-numeric RHS manifest hash changed")
                rhs_manifest = json.loads(rhs_manifest_bytes.decode("utf-8"))
                rhs_archive_path = Path(str(rhs_manifest["arrays"]["path"]))
                rhs_archive_bytes = rhs_archive_path.read_bytes()
                if (
                    _sha256_bytes(rhs_archive_bytes)
                    != _V21_REFERENCE_PRE_NUMERIC_RHS_NPZ_SHA256
                    or rhs_manifest["arrays"].get("sha256")
                    != _V21_REFERENCE_PRE_NUMERIC_RHS_NPZ_SHA256
                ):
                    raise ValueError("Z2 reference pre-numeric RHS archive hash changed")
                with np.load(rhs_archive_path, allow_pickle=False) as archive:
                    native_rhs = np.asarray(
                        archive[rhs_manifest["native_independent_rhs"]["array_key"]],
                        dtype=np.complex128,
                    )
                projected_rhs = project_unconstrained_mpc_dual(
                    np.asarray(rhs.array, dtype=np.complex128), current_native_map
                )
                independent = np.asarray(
                    current_native_map["independent_indices"], dtype=np.int64
                )
                if projected_rhs.shape[0] <= int(np.max(independent)):
                    raise ValueError("Z2 projected RHS is shorter than its native map")
                rhs_difference = projected_rhs[independent] - native_rhs
                rhs_relative = float(
                    np.linalg.norm(rhs_difference)
                    / max(np.linalg.norm(native_rhs), np.finfo(float).tiny)
                )
                if not np.isfinite(rhs_relative) or rhs_relative > 1.0e-10:
                    raise ValueError(
                        f"Z2 physical RHS differs from the matched native witness: {rhs_relative}"
                    )
                binding["v21_native_map_identity"] = native_map_facts
                binding["v21_native_rhs_identity"] = {
                    "manifest": str(rhs_manifest_path),
                    "manifest_sha256": _V21_REFERENCE_PRE_NUMERIC_RHS_JSON_SHA256,
                    "arrays_sha256": _V21_REFERENCE_PRE_NUMERIC_RHS_NPZ_SHA256,
                    "independent_rows": int(native_rhs.size),
                    "relative_difference": rhs_relative,
                    "limit": 1.0e-10,
                    "definition": (
                        "C^H of current full physical RHS compared with the saved "
                        "independent native RHS"
                    ),
                }
                del current_native_map, saved_native_map, native_rhs, projected_rhs
            candidate = binding.pop("x_ref", None)
            if candidate is None:
                raise ValueError(f"{stage} reference residual has no field vector")
            candidate = np.asarray(candidate, dtype=np.complex128)
            reference_bytes = max(int(candidate.nbytes), 1)
            # Replace the pre-load pool with the actual retained reference
            # vector plus a conservative metric scratch allowance.  The
            # allowance covers the fixed p6 storage shape, indexed error and
            # reference copies, and the metric kernel's temporary vectors.
            reference_field_temp_bytes = 6 * reference_bytes
            reference_workspace_bytes = reference_bytes + reference_field_temp_bytes
            runtime.release_workspace(reference_load_workspace_label)
            reference_load_workspace_live = False
            runtime.reserve_workspace(
                reference_workspace_label,
                reference_workspace_bytes,
            )
            reference_workspace_live = True
            reference_binding = binding
            reference_vector = candidate
            runtime.marker(
                f"{prefix}_reference_binding_loaded",
                {
                    "model": {
                        "name": reference_model.get("name"),
                        "physical_sha": reference_model.get("physical_sha"),
                        "mode_sha": reference_model.get("mode_sha"),
                    },
                    "reference_vector_bytes": reference_bytes,
                    "field_metric_temporary_allowance_bytes": reference_field_temp_bytes,
                    "retained_evaluation_workspace_bytes": reference_workspace_bytes,
                    "reference_vector_in_operator": False,
                    "reference_vector_in_initial_guess": False,
                    "evaluation_only": True,
                },
            )
            return candidate
        except V14ResourceStop:
            raise
        except (OSError, ValueError, TypeError, KeyError) as exc:
            if reference_load_workspace_live:
                runtime.release_workspace(reference_load_workspace_label)
                reference_load_workspace_live = False
            reference_error = {
                "type": type(exc).__name__,
                "message": str(exc),
            }
            raise

    def evaluate_checkpoint_field(
        iteration: int, solution: Any, residual: float
    ) -> dict[str, Any]:
        """Evaluate a saved checkpoint without influencing the live solve."""

        started = time.perf_counter()
        row: dict[str, Any] = {
            "iteration": int(iteration),
            "explicit_relative_residual": float(residual),
            "evaluation_only": True,
            "reference_authority": (
                "MATCHED_REFERENCE_AVAILABLE"
                if reference_mode == "required"
                else "MATCHED_REFERENCE_NOT_AVAILABLE"
            ),
            "reference_vector_in_operator": False,
            "reference_vector_in_initial_guess": False,
        }
        try:
            if reference_mode == "authority_limited":
                row["field_metrics"] = {}
                row["status"] = "NOT_ATTEMPTED"
            else:
                reference = evaluation_reference()
                row["field_metrics"] = _v14_p6_field_comparison(
                    common, solution, reference
                )
                row["status"] = "AVAILABLE"
        except V14ResourceStop:
            raise
        except (OSError, ValueError, TypeError, KeyError, FloatingPointError) as exc:
            row.update(
                status="EVIDENCE_INCOMPLETE",
                error={"type": type(exc).__name__, "message": str(exc)},
                field_metrics={},
            )
        row["evaluation_seconds"] = time.perf_counter() - started
        row["solve_seconds"] = solve_seconds()
        row["workflow_seconds"] = current_workflow_interval()["budget_seconds"]
        field_checkpoint_records.append(dict(row))
        append("field_checkpoint_metrics.jsonl", row)
        runtime.sample(f"{prefix}_field_checkpoint_complete")
        return row

    def solve_seconds() -> float:
        if solve_clock is None:
            raise RuntimeError("conditional solve clock was not anchored")
        return float(solve_clock.update(clock_sample())["budget_seconds"])

    def checkpoint(iteration: int, solution: Any, residual: float) -> dict[str, Any]:
        iteration = int(iteration)
        workspace_label = f"{prefix}_checkpoint_{iteration}"
        runtime.reserve_workspace(workspace_label, 8 << 20)
        try:
            runtime.sample(f"{prefix}_checkpoint_{iteration}_started")
            facts = _write_checkpoint(
                runtime.directory / "checkpoints",
                solution,
                iteration,
                residual,
                input_sha256=input_sha,
                operator_sha256=operator_sha256,
                physical_sha256=physical_sha,
                source_sha=runtime.source_sha,
                prefix=prefix,
            )
            runtime.sample(f"{prefix}_checkpoint_{iteration}_complete")
        finally:
            runtime.release_workspace(workspace_label)
        field_facts = evaluate_checkpoint_field(iteration, solution, residual)
        checkpoint_record = dict(facts)
        checkpoint_record["field_evaluation"] = field_facts
        checkpoint_records.append(checkpoint_record)
        return checkpoint_record

    def stop_requested() -> bool:
        if runtime.stop_requested:
            stop_state.update(requested=True, reason="parent_stop_requested")
            return True
        if runtime.pc_soft_stop_requested:
            stop_state.update(requested=True, reason="pc_soft_limit_requested")
            return True
        elapsed = solve_seconds()
        workflow = current_workflow_interval()["budget_seconds"]
        solve_time = v14_time_gate_facts(
            elapsed, solve_limit, time_policy, inclusive=True
        )
        workflow_time = v14_time_gate_facts(
            workflow, workflow_limit, time_policy, inclusive=True
        )
        stop_state["solve_time_gate"] = solve_time
        stop_state["workflow_time_gate"] = workflow_time
        if elapsed >= solve_limit and time_policy == V14_TIME_POLICY_ENFORCE:
            stop_state.update(requested=True, reason="solve_budget_reached")
            return True
        if workflow >= workflow_limit and time_policy == V14_TIME_POLICY_ENFORCE:
            stop_state.update(requested=True, reason="workflow_budget_reached")
            return True
        return False

    def apply_pc(source: Any) -> Any:
        sequence = len(pc_boundary_records) + 1
        runtime.begin_pc(sequence)
        value = None
        try:
            value = pc.apply(source)
        except BaseException:
            boundary = None
            boundary_error = None
            try:
                boundary = runtime.finish_pc(completed=False)
            except BaseException as exc:
                boundary_error = {"type": type(exc).__name__, "message": str(exc)}
            # An incomplete action has no valid output and cannot be returned
            # to PETSc.  The adapter owns its internal cleanup.
            value = None
            pc_boundary_records.append(
                {
                    "sequence": sequence,
                    "completed": False,
                    "runtime": boundary,
                    "runtime_error": boundary_error,
                    "pc": dict(pc.last_apply_facts),
                }
            )
            raise
        try:
            boundary = runtime.finish_pc(completed=True)
        except BaseException as exc:
            if value is not None:
                value.destroy()
            pc_boundary_records.append(
                {
                    "sequence": sequence,
                    "completed": True,
                    "runtime": None,
                    "runtime_error": {
                        "type": type(exc).__name__,
                        "message": str(exc),
                    },
                    "return_destroyed": True,
                    "pc": dict(pc.last_apply_facts),
                }
            )
            raise
        pc_boundary_records.append(
            {
                "sequence": sequence,
                "completed": True,
                "runtime": boundary,
                "pc": dict(pc.last_apply_facts),
            }
        )
        return value

    stack_context = (
        _v14_interface_live_stack(
            runtime,
            common,
            resolved_payload,
            stage=stage,
        )
        if stack_factory is None
        else stack_factory(
            runtime,
            common,
            resolved_payload,
            stage=stage,
        )
    )
    with owned_p6_vectors(), stack_context as stack:
        if p4_stack_ready_hook is not None:
            p4_stack_ready_hook(stack)
        if stack.get("operator_identity") is not None:
            identity = dict(stack["operator_identity"])
            operator_sha256 = str(stack["operator_identity_sha256"])
        else:
            identity, operator_sha256 = _v14_operator_identity(
                common, resolved_payload, stack["partition"], stage=stage
            )
        identity_packet = _save_packet(
            runtime.directory,
            f"{prefix}_operator_identity",
            {
                "schema": "task039extra.v14.fresh-p6-operator-identity-packet.v1",
                "identity": identity,
                "operator_identity_sha256": operator_sha256,
                "reference_used_for_operator_or_initial_guess": False,
            },
            runtime=runtime,
        )
        runtime.marker(
            f"{prefix}_fresh_operator_identity_complete",
            {"identity": identity, "operator_identity_sha256": operator_sha256},
        )

        rhs, rhs_facts = build_physical_rhs(common["fine"])
        rhs_packet = _save_packet(
            runtime.directory,
            f"{prefix}_physical_rhs",
            {
                "schema": "task039extra.v14.fresh-p6-rhs-packet.v1",
                "identity": identity,
                "rhs_facts": rhs_facts,
                "rhs_storage": np.asarray(rhs.array).copy(),
            },
            runtime=runtime,
        )
        runtime.marker(f"{prefix}_physical_rhs_complete", {"packet": rhs_packet})

        pc = None
        positive = None
        pc_facts: dict[str, Any] = {}
        def current_pc_facts() -> dict[str, Any]:
            if pc is None:
                return {}
            balanced = pc.balanced
            facts = {
                "apply_count": int(pc.apply_count),
                "native_A4_action_count": int(pc.native_A4_count),
                "total_counts": dict(balanced.total_counts),
                "total_operation_seconds": dict(balanced.total_operation_seconds),
                "last_apply_facts": dict(pc.last_apply_facts),
                "coarse_calls": list(pc.coarse_calls),
                "ledger": {
                    "A_count": int(pc.ledger.A_count),
                    "PH_count": int(pc.ledger.PH_count),
                    "audit_count": int(pc.ledger.audit_count),
                    "A_seconds": float(pc.ledger.A_seconds),
                    "PH_seconds": float(pc.ledger.PH_seconds),
                },
                "h6_apply_count": int(positive["h6"].apply_count)
                if positive is not None
                else None,
                "h6_facts": dict(positive["light_facts"])
                if positive is not None
                else {},
                "boundary_records": list(pc_boundary_records),
            }
            fint = stack.get("fint")
            if fint is not None and hasattr(fint, "apply_count"):
                facts.update(
                    {
                        "p4_f4_apply_count": int(fint.apply_count),
                        "p4_f4_apply_count_semantics": (
                            "physical_F4_calls_including_repairs"
                        ),
                        "p4_logical_apply_count": int(
                            getattr(fint, "logical_apply_count", 0)
                        ),
                        "p4_logical_apply_attempt_count": int(
                            getattr(fint, "logical_apply_attempt_count", 0)
                        ),
                    }
                )
            return facts

        def formal_release_timing_facts() -> dict[str, Any]:
            """Snapshot cumulative V24 costs before release destroys owners."""

            if pc is None or positive is None:
                raise RuntimeError("V24 release timing requested without live PC")
            fint = stack["fint"]
            inverse = getattr(fint, "inverse", None)
            timing = getattr(inverse, "timing_cumulative", None)
            if not isinstance(timing, Mapping):
                raise RuntimeError("V24 p4 cumulative timing is unavailable")
            fine_audit = dict(common["fine"]["physical_action"].audit)
            p4_audit = dict(common["p4"]["physical_action"].audit)
            candidate_action = getattr(pc, "_pc_fine_action", None)
            candidate_audit = (
                dict(candidate_action.audit)
                if candidate_action is not None
                else {}
            )
            candidate_facts = dict(getattr(pc, "_pc_fine_action_facts", {}))
            h6 = positive["h6"]
            h6_light_facts = dict(positive["light_facts"])
            routing = dict(getattr(common["transfer"], "routing_costs", {}))
            return {
                "schema": "task039extra.v24.formal-release-timing.v1",
                "release_boundary": "before_v20_preconditioner_release",
                "native_A6": {
                    "apply_count": int(fine_audit["apply_count"]),
                    "operation_seconds_cumulative": dict(
                        fine_audit["operation_seconds_cumulative"]
                    ),
                },
                "native_A6_witness": {
                    "role": "independent_official_residual_authority",
                    "audit": fine_audit,
                },
                "candidate_pc_internal_A6": {
                    "role": getattr(pc, "_pc_fine_action_role", "unknown"),
                    "construction_facts": candidate_facts,
                    "live_audit": candidate_audit,
                    "timing_scope": (
                        "FullspacePhysicalAction dtn/volume totals; nested volume "
                        "component timing includes explicit input MPC, R^H, and ghost "
                        "segments from FullspaceMpcFormAction"
                    ),
                },
                "native_A4": {
                    "action_count": int(pc.native_A4_count),
                    "seconds_cumulative": float(pc.native_A4_seconds),
                    "operator_action": {
                        "apply_count": int(p4_audit["apply_count"]),
                        "operation_seconds_cumulative": dict(
                            p4_audit["operation_seconds_cumulative"]
                        ),
                    },
                },
                "owner_P_PH": {
                    "route": routing["route"],
                    "primal_count": int(routing["primal_count"]),
                    "adjoint_count": int(routing["adjoint_count"]),
                    "primal_seconds": float(routing["primal_seconds"]),
                    "adjoint_seconds": float(routing["adjoint_seconds"]),
                    "route_seconds": float(routing["route_seconds"]),
                },
                "BAL_H": {
                    "counts": dict(pc.balanced.total_counts),
                    "operation_seconds_cumulative": dict(
                        pc.balanced.total_operation_seconds
                    ),
                    "ledger": {
                        "A_count": int(pc.ledger.A_count),
                        "PH_count": int(pc.ledger.PH_count),
                        "A_seconds": float(pc.ledger.A_seconds),
                        "PH_seconds": float(pc.ledger.PH_seconds),
                    },
                },
                "p4": {
                    **{
                        key: float(timing[key])
                        for key in (
                            "reduce_seconds",
                            "solve_seconds",
                            "recover_seconds",
                            "elapsed_seconds",
                        )
                    },
                    "physical_f4_call_count": int(fint.apply_count),
                    "logical_p4_call_count": int(fint.logical_apply_count),
                    "actual_mat_solve_count": int(inverse.solve_count),
                },
                "h6_apply_count": int(positive["h6"].apply_count),
                "h6": {
                    "apply_count": int(h6.apply_count),
                    "matrix_mult_count": int(h6.matrix_mult_count),
                    "power_matrix_mult_count": int(h6.power_matrix_mult_count),
                    "matrix_mult_seconds": float(h6.matrix_mult_seconds),
                    "power_matrix_mult_seconds": float(
                        h6.power_matrix_mult_seconds
                    ),
                    "apply_seconds": float(h6.apply_seconds),
                    "light_facts": h6_light_facts,
                },
            }

        lifecycle_boundary(
            "h6_outer_setup_start",
            stage=stage,
            coarse_degree=int(common.get("coarse_degree", 4)),
            includes="live H6 setup and retained outer adapter setup",
        )
        with _v14_balanced_adapter(
            runtime,
            common,
            stack["fint"],
            capture_vectors=False,
            repair_policy=p4_repair_policy,
            repair_vector_sink=p4_repair_vector_sink,
            repair_vector_capture=p4_repair_vector_capture,
            logical_apply_hook=p4_logical_apply_hook,
            pc_fine_action_factory=pc_fine_action_factory,
            packed_power10=packed_power10,
            sum_factorized_work=sum_factorized_work,
            sum_factorized_power10=sum_factorized_power10,
            direct_selected_backend=direct_selected_backend,
            reuse_projection_work=reuse_projection_work,
        ) as (pc, positive):
            if outer_adapter_factory is not None:
                # X1 checks and its one PC call share the actual X2 objects.
                # This setup is outside the solve clock but inside workflow
                # time; the adapter stays alive through final field output.
                outer_factory_kwargs = {
                    "p4_identity_sha256": operator_sha256,
                    "pc_counts": lambda: _pc_count_facts(
                        pc,
                        stack,
                        positive,
                        p4_repair_policy,
                    ),
                }
                # The new count contract is opt-in.  Legacy factories in
                # older profiles are intentionally not required to accept the
                # V24-only keyword.
                if _p4_repair_enabled(p4_repair_policy):
                    outer_factory_kwargs["p4_count_policy"] = "bounded_repair_v24"
                if v25_coarse_stage and stage == "Q4_ORIGINAL":
                    outer_factory_kwargs["first_direction_pair_context"] = {
                        "pc": pc,
                        "positive": positive,
                    }
                outer_adapter = outer_adapter_factory(
                    runtime,
                    common,
                    resolved_payload,
                    rhs,
                    apply_pc,
                    **outer_factory_kwargs,
                )
                outer_factory_kwargs.pop("first_direction_pair_context", None)
                outer_adapter.setup_checks()
                if v25_coarse_stage:
                    outer_adapter.actual_first_arnoldi_check()
                identity = {**identity, "retained_p6": outer_adapter.identity,
                            "initial_guess": "zero_retained_y; full_field_contains_internal_rhs_particular"}
                operator_sha256 = _sha256_bytes(
                    json.dumps(_jsonable(identity), sort_keys=True, separators=(",", ":")).encode()
                )
                identity_packet = _save_packet(
                    runtime.directory, f"{prefix}_dual_operator_identity",
                    {"identity": identity, "operator_identity_sha256": operator_sha256},
                    runtime=runtime,
                )
            lifecycle_boundary(
                "setup_end",
                stage=stage,
                h6_setup_complete=True,
                retained_adapter_setup_complete=outer_adapter is not None,
            )
            # H6 setup is complete at this point.  Only now does the single
            # outer solve clock begin, and the KSP vector estimate joins the
            # already-live BAL_H workspace in the same shared 1 GiB pool.
            runtime.begin_outer_solve()
            outer_active = True
            solve_clock = ClockBudget(clock_sample(), policy=CONSERVATIVE_REALTIME)
            restart = 32
            outer_workspace_bytes = _v14_outer_krylov_workspace_bytes(
                int((rhs if outer_adapter is None else outer_adapter.rhs).getLocalSize()),
                restart=restart,
            )
            runtime.reserve_workspace(outer_workspace_label, outer_workspace_bytes)
            outer_workspace_live = True
            if release_after_final_residual:
                runtime.marker(
                    "v20_outer_ksp_started",
                    {
                        "stage": stage,
                        "setup_checks_complete": bool(
                            outer_adapter is not None
                            and outer_adapter.checks.get("status") == "PASS"
                        ),
                        "begin_outer_solve": True,
                        "outer_workspace_bytes": outer_workspace_bytes,
                        "h6_and_bal_h_live": True,
                        "p4_factor_live": True,
                        "p6_cache_live": True,
                    },
                )
            lifecycle_boundary(
                "outer_adapter_started",
                stage=stage,
                zero_start=True,
                retained_space=outer_adapter is not None,
            )
            try:
                if outer_adapter is None:
                    solve_result = run_balanced_fgmres(
                        rhs, apply_fine, apply_pc,
                        checkpoint=checkpoint, append=append, seconds=solve_seconds,
                        resource_sample=lambda: runtime.sample(f"{prefix}_solve_resource"),
                        stop_requested=stop_requested, screen_enabled=True,
                        solve_limit_seconds=solve_limit, v14_policy=True, time_policy=time_policy,
                    )
                else:
                    solve_result = outer_adapter.solve(
                        checkpoint=checkpoint, append=append, seconds=solve_seconds,
                        resource_sample=lambda: runtime.sample(f"{prefix}_solve_resource"),
                        stop_requested=stop_requested,
                    )
                final_solution = solve_result["final_solution"]
            except BaseException as exc:
                # Persist the counters and completed checkpoints before the
                # enclosing cleanup path destroys BAL_H, so an interrupted
                # run remains auditable even when no worker summary is made.
                pc_facts = current_pc_facts()
                failure = {
                    "schema": "task039extra.v14.fresh-p6-solve-failure.v1",
                    "stage": stage,
                    "error": {"type": type(exc).__name__, "message": str(exc)},
                    "checkpoint_records": list(checkpoint_records),
                    "field_checkpoint_records": list(field_checkpoint_records),
                    "pc_boundary_records": list(pc_boundary_records),
                    "pc": pc_facts,
                    "outer_workspace_bytes": outer_workspace_bytes,
                }
                try:
                    failure["packet"] = _save_packet(
                        runtime.directory / "solve_failure",
                        f"{prefix}_outer",
                        failure,
                        runtime=runtime,
                    )
                except BaseException as save_exc:
                    failure["packet_error"] = {
                        "type": type(save_exc).__name__,
                        "message": str(save_exc),
                    }
                try:
                    runtime.marker(f"{prefix}_outer_solve_failed", failure)
                except BaseException:
                    pass
                raise
            finally:
                lifecycle_boundary(
                    "outer_adapter_ended",
                    stage=stage,
                    completed=solve_result is not None,
                )
            pc_facts = current_pc_facts()

        if solve_result is None:
            raise RuntimeError(f"{stage} outer FGMRES returned no result")
        final_solution = solve_result["final_solution"]

        lifecycle_boundary(
            "final_native_check_started",
            stage=stage,
            action="independent native A6 residual and packet",
        )
        # This is the one independent post-KSP A6 action.  It is deliberately
        # separate from the solver's monitor snapshots and is the only residual
        # used to authorize output recovery below.
        final_applied = rhs.duplicate()
        common["fine"]["physical_action"].apply(final_solution, final_applied)
        final_residual = rhs.copy()
        final_residual.axpy(-1.0, final_applied)
        rhs_norm = max(float(rhs.norm()), np.finfo(float).tiny)
        final_explicit_relative = float(final_residual.norm()) / rhs_norm
        if not np.isfinite(final_explicit_relative):
            raise FloatingPointError(f"{stage} independent A6 residual is nonfinite")
        final_residual_packet = _save_packet(
            runtime.directory / "final_residual",
            f"{prefix}_final",
            {
                "schema": "task039extra.v14.fresh-p6-final-residual-packet.v1",
                "identity": identity,
                "rhs_norm": rhs_norm,
                "independent_action_count": 1,
                "explicit_relative_residual": final_explicit_relative,
                "solver_reported_final_true_residual": solve_result[
                    "final_true_residual"
                ],
                "rhs": np.asarray(rhs.array).copy(),
                "solution": np.asarray(final_solution.array).copy(),
                "applied": np.asarray(final_applied.array).copy(),
                "residual": np.asarray(final_residual.array).copy(),
            },
            runtime=runtime,
        )
        runtime.marker(
            f"{prefix}_independent_final_residual_complete",
            {
                "packet": final_residual_packet,
                "relative": final_explicit_relative,
            },
        )
        lifecycle_boundary(
            "final_native_check_ended",
            stage=stage,
            relative=final_explicit_relative,
        )
        if release_after_final_residual:
            lifecycle_boundary(
                "release_check_started",
                stage=stage,
                includes="post-residual release and post-release residual gate",
            )
            if formal_release_timing:
                release_timing_facts = formal_release_timing_facts()
                runtime.marker(
                    "v24_formal_release_timing_before_release",
                    release_timing_facts,
                )
            release_result = _run_v20_release_after_final_residual(
                runtime,
                common,
                stack,
                outer_adapter,
                stage=stage,
                prefix=prefix,
                identity=identity,
                solve_result=solve_result,
                final_solution=final_solution,
                rhs=rhs,
                rhs_norm=rhs_norm,
                final_explicit_relative=final_explicit_relative,
                release_after_final_residual=release_after_final_residual,
            )
            assert release_result is not None
            release_gate_facts = release_result["release_gate"]
            release_facts = release_result["release_facts"]
            post_release_applied = release_result["post_release_applied"]
            post_release_residual = release_result["post_release_residual"]
            post_release_relative = release_result["post_release_relative"]
            post_release_residual_packet = release_result[
                "post_release_residual_packet"
            ]
            lifecycle_boundary(
                "release_check_ended",
                stage=stage,
                post_release_relative=post_release_relative,
            )
        # Freeze the solve-clock evidence here.  Reading historical files and
        # assembling the later report is workflow time, not solve time.
        solve_clock_interval = dict(solve_clock.update(clock_sample()))
        # The solve clock covers KSP, BAL_H, checkpoint field comparisons and
        # the independent final A6 action/packet.  Close it only after that
        # final residual checkpoint, before any official output recovery.
        if outer_active:
            try:
                runtime.finish_outer_solve()
            finally:
                outer_active = False
        if outer_workspace_live:
            runtime.release_workspace(outer_workspace_label)
            outer_workspace_live = False
        runtime.marker(
            f"{prefix}_outer_solve_finished",
            {"after_independent_final_residual": True},
        )

        solver_facts = {
            key: value
            for key, value in solve_result.items()
            if key != "final_solution"
        }
        solver_facts["checkpoint_records"] = list(checkpoint_records)
        solver_facts["field_checkpoint_records"] = list(field_checkpoint_records)
        solver_facts["stop_state"] = dict(stop_state)
        if outer_adapter is not None:
            solver_facts["retained_outer"] = outer_adapter.facts()
        history_facts = _v14_history_facts(
            runtime.root,
            common,
            solver_facts,
            notch=notch,
            physical_sha256=physical_sha,
        )

        if stack.get("stack_facts") is not None:
            stack_facts = dict(stack["stack_facts"])
        else:
            stack_facts = {
                "schema": stack["schema"],
                "stage": stage,
                "partition": stack["partition"].audit(),
                "core": stack["core"].factor_facts,
                "representative_patches": stack["representative_facts"],
                "delta": stack["delta_facts"],
                "local_smoother": stack["local_audit"],
                "action_checks": stack["action_checks"],
                "candidate": stack["candidate_facts"],
                "paired_basis": stack["paired_facts"],
                "coarse_pair": stack["coarse_pair"].audit(),
                "global_interface_matrix_built": False,
                "global_dense_schur_constructed": False,
                "explicit_schur_released_before_outer_solve": True,
            }
        core = stack.get("core")
        internal_factor_count = stack.get("internal_factor_count")
        if internal_factor_count is None and core is not None:
            internal_factor_count = len(core.internal)
        base_record = {
            "schema": f"task039extra.v14.{stage.lower()}.v2",
            "stage": stage,
            "predecessor": dict(predecessor),
            "operator_identity": identity,
            "operator_identity_sha256": operator_sha256,
            "operator_identity_packet": identity_packet,
            "native_aq_projection_check": _jsonable(
                common.get("native_aq_projection_check")
            ),
            "rhs_packet": rhs_packet,
            "rhs_facts": rhs_facts,
            "interface_stack": stack_facts,
            "delta": stack_facts.get("delta", {}),
            "lifecycle": {
                "internal_factor_count": int(internal_factor_count or 0),
                "outer_krylov_workspace_bytes": outer_workspace_bytes,
                "outer_krylov_workspace_scope": (
                    "derived upper-count estimate for FGMRES32 basis, action, "
                    "preconditioner and explicit-residual vectors"
                ),
                "outer_solve_finished_after_independent_final_residual": True,
                "ksp_phase": solver_facts.get("ksp_phase"),
                "ksp_phase_time_source": (
                    "run_retained_fgmres.ksp_phase or solver-native phase record; "
                    "not the outer_adapter interval"
                ),
            },
            "solver": solver_facts,
            **time_policy_facts,
            "pc": pc_facts,
            "pc_boundary_contract": {
                "route": "BAL_H",
                "coarse_calls_per_apply": 2,
                "fint_direct": True,
                "inner_ksp": False,
                "restart": 32,
                "max_it": 2048,
                "zero_start": True,
                "soft_pc_seconds": float(resources["pc_soft_seconds"]),
                "hard_pc_seconds": float(resources["pc_hard_seconds"]),
            },
            "final_residual": final_residual_packet,
            "final_explicit_relative_residual": final_explicit_relative,
            "post_release_final_residual": post_release_residual_packet,
            "post_release_explicit_relative_residual": post_release_relative,
            "release_after_final_residual": bool(release_after_final_residual),
            "release_facts": release_facts,
            "formal_release_timing": release_timing_facts,
            "history": history_facts,
            "stop_state": dict(stop_state),
            "reference_evaluation": {
                "authority": (
                    "MATCHED_REFERENCE_AVAILABLE"
                    if reference_mode == "required"
                    else "MATCHED_REFERENCE_NOT_AVAILABLE"
                ),
                "mode": reference_mode,
                "attempted": reference_attempted,
                "loaded": reference_binding is not None and reference_vector is not None,
                "error": reference_error,
                "load_workspace_bytes": reference_load_workspace_bytes,
                "retained_workspace_bytes": reference_workspace_bytes,
                "field_metric_temporary_allowance_bytes": reference_field_temp_bytes,
                "checkpoint_count": len(field_checkpoint_records),
                "checkpoint_records": list(field_checkpoint_records),
                "evaluation_only": True,
            },
            "fresh_numerical_stack": True,
            "reused_structural_maps_only": True,
            "reused_numeric_factor": False,
            "reused_interface_directions": False,
        }

        solver_status = str(solver_facts.get("status", ""))
        solver_elapsed = float(solver_facts.get("elapsed_seconds", np.nan))
        solve_clock_seconds = float(
            solve_clock_interval.get("budget_seconds", np.nan)
        )
        solver_time_finite = bool(
            np.isfinite(solver_elapsed) and solver_elapsed >= 0.0
        )
        solve_clock_time_finite = bool(
            np.isfinite(solve_clock_seconds) and solve_clock_seconds >= 0.0
        )
        solver_time_gate = (
            v14_time_gate_facts(solver_elapsed, solve_limit, time_policy)
            if solver_time_finite
            else None
        )
        solve_clock_time_gate = (
            v14_time_gate_facts(solve_clock_seconds, solve_limit, time_policy)
            if solve_clock_time_finite
            else None
        )
        solver_gate = bool(
            solver_status == "TRUE_RESIDUAL_PASS"
            and np.isfinite(float(solver_facts.get("final_true_residual", np.nan)))
            and float(solver_facts["final_true_residual"]) <= 1.0e-6
            and final_explicit_relative <= 1.0e-6
            and solver_time_finite
            and solver_time_gate is not None
            and solver_time_gate["passed"]
            and solve_clock_time_finite
            and solve_clock_time_gate is not None
            and solve_clock_time_gate["passed"]
            and (
                not release_after_final_residual
                or (
                    post_release_relative is not None
                    and post_release_relative <= 1.0e-6
                )
            )
        )
        base_record["gates"] = {
            "solver_status": solver_status,
            "solver_reported_true_residual": solver_facts.get(
                "final_true_residual"
            ),
            "independent_final_explicit_relative_residual": final_explicit_relative,
            "post_release_final_explicit_relative_residual": post_release_relative,
            "post_release_residual_gate": (
                not release_after_final_residual
                or (
                    post_release_relative is not None
                    and post_release_relative <= 1.0e-6
                )
            ),
            "solver_gate": solver_gate,
            "solve_clock_interval": solve_clock_interval,
            "solve_time_within_limit": bool(
                solver_time_finite and not solver_time_gate["exceeded"]
            ) if solver_time_gate is not None else False,
            "solve_time_qualified": bool(
                solver_time_gate is not None and solver_time_gate["passed"]
            ),
            "solve_time_exceeded": bool(
                solver_time_gate is not None and solver_time_gate["exceeded"]
            ),
            "solve_clock_within_limit": bool(
                solve_clock_time_finite and not solve_clock_time_gate["exceeded"]
            ) if solve_clock_time_gate is not None else False,
            "solve_clock_time_qualified": bool(
                solve_clock_time_gate is not None and solve_clock_time_gate["passed"]
            ),
            "solve_clock_time_exceeded": bool(
                solve_clock_time_gate is not None and solve_clock_time_gate["exceeded"]
            ),
            "solve_time_gate": solver_time_gate,
            "solve_clock_time_gate": solve_clock_time_gate,
            **time_policy_facts,
        }
        if not solver_gate:
            performance_statuses = {
                "PERFORMANCE_CONTROLLED_STOP",
                "V14_PROGRESS_SCREEN_STOP",
                "NORMAL_SCREEN_STOP",
                "PROGRESS_INSUFFICIENT_AT_MID_BUDGET",
                "ITERATION_BUDGET_EXHAUSTED",
            }
            controlled = solver_status in performance_statuses or bool(
                stop_state.get("requested")
            )
            base_record.update(
                {
                    "status": (
                        f"{stage}_PERFORMANCE_CONTROLLED_STOP"
                        if controlled
                        else f"{stage}_FULLSPACE_RESIDUAL_GATE_FAIL"
                    ),
                    "official_result": False,
                    "stage_pass": False,
                    "result_classification": (
                        "PERFORMANCE_CONTROLLED_STOP"
                        if controlled
                        else "FULLSPACE_RESIDUAL_GATE_FAIL"
                    ),
                    "output_role": "diagnostic_solution_only",
                    "field": {},
                    "comparison": {
                        "status": "NOT_EVALUATED_RESIDUAL_GATE"
                    },
                    "physical_checks": {},
                }
            )
            attach_lifecycle(base_record)
            runtime.marker(f"{prefix}_fullspace_residual_gate_failed", base_record)
            return base_record

        if reference_mode == "authority_limited":
            # B/C have no matched field reference.  Output recovery remains
            # downstream of the same independent residual and release gates;
            # only the reference-comparison branch is replaced by explicit
            # finite/closure/identity checks.
            lifecycle_boundary(
                "official_postprocess_started",
                stage=stage,
                mode="authority_limited",
            )
            runtime.set_phase("evaluation")
            output_dir = runtime.directory / "numerical_output"
            runtime.sample(f"{prefix}_before_output_recovery")
            output = recover_p0_outputs(
                common["fine"],
                final_solution,
                output_dir,
                export_all_port_modes=True,
                jit_options=official_jit_options,
            )
            output_packet = _save_packet(
                runtime.directory / "official_output",
                f"{prefix}_output",
                {
                    "schema": "task039extra.v21.authority-limited-output-packet.v1",
                    "identity": identity,
                    "output": output,
                },
                runtime=runtime,
            )
            runtime.marker(
                f"{prefix}_authority_limited_output_complete",
                {"packet": output_packet},
            )
            runtime.sample(f"{prefix}_output_recovery_complete")
            resource_facts = _v14_resource_facts(runtime)
            workflow_interval = current_workflow_interval()
            workflow_seconds = float(
                workflow_interval.get("budget_seconds", np.nan)
            )
            workflow_time_gate = (
                v14_time_gate_facts(workflow_seconds, workflow_limit, time_policy)
                if np.isfinite(workflow_seconds) and workflow_seconds >= 0.0
                else None
            )
            authority_checks, authority_facts = _v21_authority_limited_checks(
                solver_facts,
                output,
                post_release_relative=post_release_relative,
                common=common,
                output_dir=output_dir,
            )
            authority_checks["solver_gate"] = bool(
                base_record["gates"].get("solver_gate")
            )
            resource_pass = bool(resource_facts.get("gate"))
            workflow_pass = bool(
                workflow_time_gate is not None and workflow_time_gate["passed"]
            )
            stage_pass = bool(
                all(authority_checks.values()) and resource_pass and workflow_pass
            )
            base_record.update(
                {
                    "status": (
                        f"{stage}_AUTHORITY_LIMITED_PASS"
                        if stage_pass
                        else f"{stage}_CONSISTENCY_GATE_FAIL"
                    ),
                    "official_result": stage_pass,
                    "stage_pass": stage_pass,
                    "result_classification": (
                        "DISCRETE_SOLVE_AND_CONSISTENCY_PASS_AUTHORITY_LIMITED"
                        if stage_pass
                        else "AUTHORITY_LIMITED_CONSISTENCY_GATE_FAIL"
                    ),
                    "output_role": (
                        "official_authority_limited"
                        if stage_pass
                        else "diagnostic_only"
                    ),
                    "reference_authority": "MATCHED_REFERENCE_NOT_AVAILABLE",
                    "field": {},
                    "comparison": {
                        "status": "MATCHED_REFERENCE_NOT_AVAILABLE",
                        "reference_evaluation_attempted": False,
                    },
                    "authority_limited_checks": authority_facts,
                    "physical_checks": authority_checks,
                    "output": output_packet,
                    "output_facts": {
                        key: value for key, value in output.items() if key != "auxiliary"
                    },
                    "reference_binding": None,
                    "resource": resource_facts,
                    "workflow_clock_interval": workflow_interval,
                    "gates": {
                        **base_record["gates"],
                        "authority_limited_checks_pass": bool(
                            all(authority_checks.values())
                        ),
                        "resource_prefix_pass": resource_pass,
                        "workflow_pass": workflow_pass,
                        "workflow_within_limit": bool(
                            workflow_time_gate is not None
                            and not workflow_time_gate["exceeded"]
                        ),
                        "workflow_time_qualified": workflow_pass,
                        "workflow_time_exceeded": bool(
                            workflow_time_gate is not None
                            and workflow_time_gate["exceeded"]
                        ),
                        "workflow_time_gate": workflow_time_gate,
                        **time_policy_facts,
                        "stage_pass": stage_pass,
                    },
                }
            )
            lifecycle_boundary(
                "official_postprocess_ended",
                stage=stage,
                mode="authority_limited",
                stage_pass=stage_pass,
            )
            attach_lifecycle(base_record)
            runtime.marker(f"{prefix}_fullspace_stage_complete", base_record)
            return base_record

        lifecycle_boundary(
            "official_postprocess_started",
            stage=stage,
            mode="matched_reference",
        )
        runtime.set_phase("evaluation")
        terminal_field_records = [
            item
            for item in field_checkpoint_records
            if int(item.get("iteration", -1))
            == int(solver_facts.get("iterations", -2))
        ]
        terminal_field = (
            terminal_field_records[-1] if terminal_field_records else None
        )
        if (
            reference_error is not None
            or reference_binding is None
            or reference_vector is None
            or terminal_field is None
            or terminal_field.get("status") != "AVAILABLE"
            or not terminal_field.get("field_metrics")
        ):
            evaluation_error = reference_error
            if evaluation_error is None and terminal_field is not None:
                evaluation_error = terminal_field.get("error")
            if evaluation_error is None:
                evaluation_error = {
                    "type": "MissingCheckpointEvaluation",
                    "message": (
                        "the terminal checkpoint did not retain an evaluation-only "
                        "reference field comparison"
                    ),
                }
            base_record.update(
                {
                    "status": f"{stage}_REFERENCE_EVIDENCE_INCOMPLETE",
                    "official_result": False,
                    "stage_pass": False,
                    "result_classification": "EVIDENCE_INCOMPLETE",
                    "output_role": "diagnostic_solution_only",
                    "reference_error": evaluation_error,
                    "field": {},
                    "comparison": {"status": "REFERENCE_EVIDENCE_INCOMPLETE"},
                    "physical_checks": {},
                }
            )
            lifecycle_boundary(
                "official_postprocess_ended",
                stage=stage,
                mode="matched_reference",
                stage_pass=False,
            )
            attach_lifecycle(base_record)
            runtime.marker(f"{prefix}_reference_binding_failed", base_record)
            return base_record

        # The terminal checkpoint was evaluated immediately after its complete
        # solution was written.  Reuse those norms; no second metric or
        # reference load is performed after the residual gate.
        field = dict(terminal_field["field_metrics"])
        base_record["reference_evaluation"]["terminal_field_reused"] = True
        output_dir = runtime.directory / "numerical_output"
        runtime.sample(f"{prefix}_before_output_recovery")
        output = recover_p0_outputs(
            common["fine"],
            final_solution,
            output_dir,
            export_all_port_modes=True,
            jit_options=official_jit_options,
        )
        output_packet = _save_packet(
            runtime.directory / "official_output",
            f"{prefix}_output",
            {
                "schema": "task039extra.v14.fresh-p6-output-packet.v1",
                "identity": identity,
                "output": output,
            },
            runtime=runtime,
        )
        comparison = _compare_saved_output(
            output,
            reference_binding["reference_output"],
            current_dir=output_dir,
            reference_dir=Path(reference_binding["reference_output_dir"]),
        )
        runtime.marker(
            f"{prefix}_physical_output_comparison_complete",
            {"packet": output_packet, "comparison": comparison},
        )
        runtime.sample(f"{prefix}_output_recovery_complete")
        resource_facts = _v14_resource_facts(runtime)
        workflow_interval = current_workflow_interval()
        workflow_seconds = float(workflow_interval.get("budget_seconds", np.nan))
        workflow_time_gate = (
            v14_time_gate_facts(workflow_seconds, workflow_limit, time_policy)
            if np.isfinite(workflow_seconds) and workflow_seconds >= 0.0
            else None
        )
        physical_checks = _v14_physical_checks(
            solver_facts, field, comparison, time_policy=time_policy
        )
        physical_pass = bool(physical_checks) and all(
            bool(value) for value in physical_checks.values()
        )
        resource_pass = bool(resource_facts.get("gate"))
        workflow_pass = bool(
            workflow_time_gate is not None and workflow_time_gate["passed"]
        )
        stage_pass = bool(physical_pass and resource_pass and workflow_pass)
        base_record.update(
            {
                "status": (
                    f"{stage}_FULLSPACE_OFFICIAL_PASS"
                    if stage_pass
                    else f"{stage}_PHYSICAL_OUTPUT_GATE_FAIL"
                ),
                "official_result": stage_pass,
                "stage_pass": stage_pass,
                "result_classification": (
                    "DISCRETE_SOLVER_OUTPUT_PASS"
                    if stage_pass
                    else "PHYSICAL_OUTPUT_GATE_FAIL"
                ),
                "output_role": "official" if stage_pass else "diagnostic_only",
                "field": field,
                "comparison": comparison,
                "physical_checks": physical_checks,
                "output": output_packet,
                "output_facts": {
                    key: value for key, value in output.items() if key != "auxiliary"
                },
                "reference_binding": reference_binding,
                "resource": resource_facts,
                "workflow_clock_interval": workflow_interval,
                "gates": {
                    **base_record["gates"],
                    "physical_checks_pass": physical_pass,
                    "resource_prefix_pass": resource_pass,
                    "workflow_pass": workflow_pass,
                    "workflow_within_limit": bool(
                        workflow_time_gate is not None
                        and not workflow_time_gate["exceeded"]
                    ),
                    "workflow_time_qualified": workflow_pass,
                    "workflow_time_exceeded": bool(
                        workflow_time_gate is not None
                        and workflow_time_gate["exceeded"]
                    ),
                    "workflow_time_gate": workflow_time_gate,
                    **time_policy_facts,
                    "stage_pass": stage_pass,
                },
            }
        )
        lifecycle_boundary(
            "official_postprocess_ended",
            stage=stage,
            mode="matched_reference",
            stage_pass=stage_pass,
        )
        attach_lifecycle(base_record)
        runtime.marker(f"{prefix}_fullspace_stage_complete", base_record)
        return base_record


def _q6_finalize(runtime: _V14Runtime) -> dict[str, Any]:
    """Summarize existing attempts without substituting missing data for failure."""

    ledger_data = Path(runtime._ledger_path).read_bytes()
    ledger = json.loads(ledger_data)
    if ledger["batch_identity"] != "review_v14":
        raise ValueError("Q6 requires the unchanged review_v14 ledger")
    effective_budget = read_v14_effective_budget(ledger)
    recovery_events = [
        event for event in ledger.get("infrastructure_recoveries", [])
        if isinstance(event, Mapping)
        and event.get("recovery_id") == "V15_Q0_EIO_ONCE"
        and event.get("actual_elapsed_seconds") is None
        and event.get("historical_terminal_coverage") == "incomplete"
    ]
    historical_unknown_cost = bool(recovery_events)
    stage_names = ("Q0_CORE", "Q1_FULL_DIRECT", "Q2_SCHUR_DIRECT",
                   "Q3_INTERFACE_CONTROL", "Q4_ORIGINAL", "Q5_NOTCH")
    stages = {}
    workers = {}
    for stage in stage_names:
        stage_record = ledger.get("stages", {}).get(stage, {})
        attempts = stage_record.get("attempts", [])
        item = {"stage": stage, "attempts": attempts, "qualified": False,
                "status": "not_run", "memory": {}, "cost": {}, "numerical": {},
                "bindings": {}, "read_errors": {},
                **v14_time_policy_facts(V14_TIME_POLICY_ENFORCE)}
        stages[stage] = item
        if not attempts:
            item["reason"] = "no_recorded_attempt"
            continue
        stage_historical_unknown = stage == "Q0_CORE" and historical_unknown_cost
        attempt = attempts[-1]
        attempt_time_policy = normalize_v14_time_policy(
            attempt.get("time_policy")
        )
        directory = Path(attempt["run_directory"])
        administrative_closed = bool(
            stage == "Q0_CORE"
            and stage_historical_unknown
            and stage_record.get("active_attempt") is None
            and len(attempts) == 1
        )
        settled = (stage_record["active_attempt"] is None
                   and (attempt.get("settled_seconds") is not None or administrative_closed))
        item.update(status=("administratively_closed" if administrative_closed else
                            "settled_attempt" if settled else "unsettled_attempt"),
                    source_sha=attempt["source_sha"], run_directory=str(directory),
                    historical_unknown_cost=stage_historical_unknown,
                    historical_terminal_coverage=(
                        "incomplete" if stage_historical_unknown else "not_applicable"
                    ),
                    historical_recovery_events=(recovery_events if stage == "Q0_CORE" else []))
        item.update(v14_time_policy_facts(attempt_time_policy))
        item["time_observations"] = {
            "settled_seconds": attempt.get("settled_seconds"),
            "reserved_seconds": attempt.get("reserved_seconds"),
            "reservation_exceeded_seconds": attempt.get("reservation_exceeded_seconds"),
            "policy": attempt_time_policy,
        }
        records = {}
        for name, filename in (
            ("worker", "physical_p4_schur_v14_summary.json"),
            ("parent", "run_summary.json"), ("watchdog", "watchdog/summary.json")):
            path = directory / filename
            try:
                data = path.read_bytes()
                records[name] = json.loads(data)
                item["bindings"][str(path)] = _sha256_bytes(data)
            except (OSError, ValueError, TypeError) as exc:
                item["read_errors"][name] = f"{type(exc).__name__}: {exc}"
                records[name] = {}
        worker, parent, watchdog = (
            records[name] for name in ("worker", "parent", "watchdog")
        )
        workers[stage] = worker
        resource = _v14_resource_facts(SimpleNamespace(
            resources_path=directory / "v14_worker_resources.jsonl", workspace_cap=1 << 30,
            inventory_cap=((6 if stage in {"Q1_FULL_DIRECT", "Q2_SCHUR_DIRECT"} else 3) << 30)
            if stage != "Q0_CORE" else None))
        item["resource_trace"] = resource
        item["memory"] = {
            "full_process_tree_sampled_rss_peak_bytes": watchdog.get("sampled_process_tree_rss_peak_bytes"),
            "full_process_tree_sampled_pss_peak_bytes": watchdog.get("sampled_process_tree_pss_peak_bytes"),
            "known_inventory_peak_bytes": resource["ledger_inventory_peak_bytes"] if resource["sample_count"] and stage != "Q0_CORE" else None,
            "workspace_peak_bytes": resource["ledger_workspace_peak_bytes"] if resource["sample_count"] else None,
            "scope": "parent full workflow sampled tree peak; separate known live-object inventory",
            "final_cleanup_observed": watchdog.get("descendants_cleared") is True,
        }
        item["cost"] = {
            "settled_seconds": attempt.get("settled_seconds"),
            "actual_elapsed_seconds": attempt.get("actual_elapsed_seconds"),
            "reserved_seconds": attempt["reserved_seconds"],
            "historical_unknown_cost": stage_historical_unknown,
            "historical_recovery_events": recovery_events if stage == "Q0_CORE" else [],
            "workflow_clock_interval": parent.get("workflow_clock_interval"),
            "calls": [{"stem": row["stem"], "elapsed_seconds": row["elapsed_seconds"]}
                      for row in worker.get("solve_records", [])],
            "factor_setup": worker.get("factor", worker.get("factor_inventory")),
            "lifecycle": worker.get("lifecycle"),
            "solver": worker.get("solver"),
            "full_setup_seconds": None,
            "time_policy": attempt_time_policy,
            "time_gate_evaluated": attempt_time_policy == V14_TIME_POLICY_ENFORCE,
            "settled_within_reservation": (
                attempt.get("reservation_exceeded_seconds") is not None
                and float(attempt.get("reservation_exceeded_seconds")) <= 0.0
            ) if attempt.get("reservation_exceeded_seconds") is not None else None,
        }
        # This UTC-only duration includes preflight, assembly and conversion
        # before the first RHS. It is not substituted for the conservative
        # ledger charge or a separately measured numeric-factor timer.
        events_path = directory / "v14_events.jsonl"
        if stage in {"Q1_FULL_DIRECT", "Q2_SCHUR_DIRECT"} and events_path.is_file():
            try:
                with events_path.open(encoding="utf-8") as stream:
                    for line in stream:
                        event = json.loads(line)
                        if event["event"] == ("q1_rhs_solve_started" if stage == "Q1_FULL_DIRECT" else "q2_rhs_solve_started"):
                            item["cost"]["preflight_through_setup_utc_seconds"] = (
                                event["timestamp_ns"] - attempt["workflow_clock_start"]["utc_ns"]) / 1e9
                            break
                item["bindings"][str(events_path)] = _sha256_file(events_path)
            except (OSError, ValueError, TypeError, KeyError) as exc:
                item["read_errors"]["setup_clock"] = f"{type(exc).__name__}: {exc}"
        item["numerical"] = {key: worker.get(key) for key in (
            "status", "result_classification", "error", "solve_records", "gates",
            "field", "comparison", "balanced_p6_audit", "history",
            "final_explicit_relative_residual")}
        item["termination"] = {
            "parent_classification": parent.get("result_classification"),
            "watchdog_classification": watchdog.get("classification"),
            "leader_exit_code": watchdog.get("leader_exit_code"),
            "remaining_child_pids": watchdog.get("remaining_child_pids"),
            "settled": settled,
            **v14_time_policy_facts(attempt_time_policy),
        }
        if stage != "Q0_CORE" and settled:
            item["gate"] = _v14_settled_stage_gate(runtime, stage)
            item["qualified"] = item["gate"]["qualified"]
        item["reason"] = (
            "administrative_closure_historical_terminal_coverage_incomplete"
            if stage_historical_unknown
            else "latest_attempt_unsettled" if not settled
            else item.get("gate", {}).get("reason", "Q0_recorded_only")
        )
        item["measured_candidate_stop"] = bool(
            stage in {"Q3_INTERFACE_CONTROL", "Q4_ORIGINAL", "Q5_NOTCH"}
            and settled and worker.get("source_sha") == attempt["source_sha"]
            and watchdog.get("descendants_cleared") is True
            and watchdog.get("remaining_child_pids") == []
            and (item.get("gate", {}).get("reason") == "predecessor_numerical_gate_failed"
                 or worker.get("result_classification") in {
                     "RESOURCE_CONTROLLED_STOP", "PERFORMANCE_CONTROLLED_STOP", "PC_TIME_CONTROLLED_STOP",
                     "controlled_negative_interface_candidate", "FULLSPACE_RESIDUAL_GATE_FAIL",
                     "PHYSICAL_OUTPUT_GATE_FAIL"}))
        if (stage == "Q3_INTERFACE_CONTROL" and settled
                and worker.get("result_classification") == "WORKER_FAILED"):
            try:
                manifest = json.loads(
                    (directory / "run_manifest.json").read_text(encoding="utf-8")
                )
            except (OSError, ValueError, TypeError):
                manifest = {}
            saved_negative = _q6_saved_q3_negative_evidence(
                stage_record=stage_record,
                attempt=attempt,
                directory=directory,
                worker=worker,
                manifest=manifest,
                watchdog=watchdog,
                time_policy=attempt_time_policy,
            )
            item["saved_q3_negative_evidence"] = saved_negative
            if saved_negative.get("status") == "MEASURED_NEGATIVE_CANDIDATE":
                item["cost"]["calls"] = [
                    {"stem": value["stem"], "elapsed_seconds": value["elapsed_seconds"]}
                    for value in saved_negative["values"]
                ]
            if saved_negative["measured_candidate_stop"]:
                item["measured_candidate_stop"] = True
                item["qualified"] = False
                item["reason"] = "measured_negative_pre_balanced_q3_evidence"

    q1, q2, q3, q4, q5 = (stages[name] for name in stage_names[1:])
    memory_answer = {"status": "COMPARISON_INCONCLUSIVE", "memory_ratio": None,
                     "resident_inventory_ratio": None,
                     "reason": "needs qualified matched Q1/Q2 accuracy and full measured memory"}
    if q1["qualified"] and q2["qualified"]:
        a, b = q1["memory"], q2["memory"]
        keys = ("full_process_tree_sampled_rss_peak_bytes", "known_inventory_peak_bytes")
        values = [row[key] for row in (a, b) for key in keys]
        same_environment = workers["Q1_FULL_DIRECT"]["abi"] == workers["Q2_SCHUR_DIRECT"]["abi"]
        same_rhs = workers["Q1_FULL_DIRECT"]["rhs"] == workers["Q2_SCHUR_DIRECT"]["rhs"]
        if same_environment and same_rhs and all(isinstance(v, (int, float)) and np.isfinite(v) and v > 0 for v in values):
            ratio = b[keys[0]] / a[keys[0]]
            resident_ratio = b[keys[1]] / a[keys[1]]
            memory_answer.update(
                status=("MEANINGFUL_FIXED_CASE_MEMORY_REDUCTION" if ratio <= .9 else
                        "SMALL_OBSERVED_REDUCTION" if ratio < 1. else "NO_OBSERVED_MEMORY_REDUCTION"),
                memory_ratio=ratio, resident_inventory_ratio=resident_ratio,
                rss_difference_bytes=b[keys[0]] - a[keys[0]],
                inventory_difference_bytes=b[keys[1]] - a[keys[1]],
                reason="same ABI/RHS and full-workflow scope; setup/apply costs reported separately",
                single_case_observation_not_statistical_claim=True)
        else:
            memory_answer["reason"] = "environment/RHS mismatch or incomplete positive memory measurements"

    stopped = [name for name in stage_names[3:] if stages[name].get("measured_candidate_stop")]
    full_pass = q3["qualified"] and q4["qualified"] and q5["qualified"]
    if full_pass:
        interface_status = "FULL_ORIGINAL_AND_NOTCH_PASS"
        next_method = "RETAIN_FIXED_INTERFACE_CANDIDATE_ONE_SCALE_VALIDATION"
    elif stopped:
        interface_status = "MEASURED_FIXED_CONFIGURATION_STOP"
        next_method = "CLOSE_FIXED_INTERFACE_CONFIGURATION"
    else:
        interface_status = "EVIDENCE_INCOMPLETE"
        next_method = "COMPLETE_EXISTING_REVIEW_NO_NEW_METHOD"
    direct_resolved = all(row["status"] == "settled_attempt" and not row["read_errors"]
                          for row in (q1, q2))
    no_unsettled = all(row["status"] != "unsettled_attempt" for row in stages.values())
    complete = bool(direct_resolved and no_unsettled and (full_pass or stopped))
    record = {
        "schema": "task039extra.v14.q6-finalize.v2",
        "status": "Q6_FINALIZED" if complete else "Q6_EVIDENCE_INCOMPLETE",
        "stage_pass": complete, "official_result": False,
        "result_classification": "FINALIZATION_COMPLETE" if complete else "EVIDENCE_INCOMPLETE",
        "ledger": {"path": str(runtime._ledger_path), "sha256": _sha256_bytes(ledger_data),
                   "recorded_elapsed_seconds": ledger["elapsed_seconds"],
                   "elapsed_seconds_semantics": effective_budget["elapsed_seconds_semantics"],
                   "effective_budget": effective_budget,
                   "historical_unknown_cost": historical_unknown_cost,
                   "historical_cost_status": (
                       "UNKNOWN_HISTORICAL_ATTEMPT" if historical_unknown_cost else "KNOWN_OR_NOT_APPLICABLE"
                   ),
                   "unsettled_cost_is_not_zero": not no_unsettled},
        **v14_time_policy_facts(
            normalize_v14_time_policy(getattr(runtime, "time_policy", None))
        ),
        "time_policy_scope": "each stage uses its own attempt policy; historical missing fields default to enforce",
        "answers": {
            "exact_schur_memory": memory_answer,
            "interface_approximation": {"status": interface_status, "measured_stop_stages": stopped,
                                       "Q3_admission": q3["qualified"]},
            "full_p6": {"original_qualified": q4["qualified"], "notch_qualified": q5["qualified"]},
            "next_choice": {"status": next_method,
                            "accurate_reference_retention_supported": (
                                q1["qualified"] and q2["qualified"]
                                and memory_answer["memory_ratio"] is not None
                                and memory_answer["memory_ratio"] < 1.)},
        },
        "stages": stages, "new_pde_actions": 0, "ledger_modified": False,
        "no_missing_evidence_implies_method_failure": True,
    }
    record["packet"] = _save_packet(runtime.directory, "q6_decision", record, runtime=runtime)
    runtime.marker("q6_finalize_complete", record)
    return record


def _q0_core(runtime: _V14Runtime, common: dict[str, Any]) -> dict[str, Any]:
    volume = None
    try:
        volume = _assemble_volume(runtime, common)
        partition, _port_data = __import__(
            "src.solvers.physical_interface_schur", fromlist=["build_interface_partition"]
        ).build_interface_partition(
            common["levels"]["spaces"][4],
            common["levels"]["floquets"][4],
            common["p4"]["dtn_action"].carrier,
            volume=volume,
        )
        record = {
            "schema": "task039extra.v14.q0-core.v1",
            "status": "Q0_CORE_PASS",
            "official_result": True,
            "partition": partition.audit(),
            "levels": sorted(common["levels"]["spaces"]),
            "old_macro_objects_constructed": False,
            "old_p2_p1_levels_constructed": False,
            "global_dense_schur_constructed": False,
        }
        runtime.marker("q0_core_complete", record)
        return record
    finally:
        if volume is not None:
            volume.destroy()


def run_physical_p4_schur_v14(
    resolved_payload: Mapping[str, Any],
    run_directory: str | Path,
    *,
    source_sha: str,
) -> dict[str, Any]:
    """Run one explicit V14 stage and return the Task38 adapter result."""

    from src.io.input_validation import simulation_config_3d_from_normalized

    directory = Path(run_directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    stage = resolved_payload.get("solver", {}).get("stage")
    contract = profile_facts(SCHUR_PROFILE)
    summary: dict[str, Any] = {
        "schema": "task039extra.v14.worker-summary.v1",
        "profile": SCHUR_PROFILE,
        "stage": stage,
        "source_sha": source_sha,
        "status": "STARTED",
        "official_result": None,
    }
    runtime = None
    handlers: dict[int, Any] = {}
    rhs_records: list[dict[str, Any]] | None = None
    try:
        if resolved_payload.get("dimension") != 3:
            raise ValueError("V14 requires dimension=3")
        if resolved_payload.get("method", {}).get("kind") != "full3d_iterative":
            raise ValueError("V14 requires method.kind=full3d_iterative")
        if resolved_payload.get("solver", {}).get("preconditioner") != SCHUR_PROFILE:
            raise ValueError("V14 worker received a different preconditioner")
        if resolved_payload.get("derived", {}).get("physical_intermediate_profile") != contract:
            raise ValueError("V14 resolved profile differs from the frozen contract")
        if not isinstance(source_sha, str) or len(source_sha) != 40:
            raise ValueError("V14 requires the complete launch source SHA")
        abi = _abi_facts()
        summary["abi"] = abi
        cfg = simulation_config_3d_from_normalized(resolved_payload)
        root = _repo_root()
        runtime = _V14Runtime(
            directory,
            str(stage),
            contract,
            root=root,
            source_sha=source_sha,
        )
        summary["shared_budget"] = runtime.shared_budget
        summary["shared_attempt"] = {
            "attempt_index": runtime._stage_attempt_index,
            "reserved_seconds": runtime.workflow_reserved_seconds,
            "recovery_id": runtime.shared_attempt.get("recovery_id"),
            "infrastructure_recovery": runtime.infrastructure_recovery,
            **runtime.time_policy_facts,
        }
        summary.update(runtime.time_policy_facts)
        for signum in (signal.SIGTERM, signal.SIGINT):
            handlers[signum] = signal.signal(
                signum, lambda _value, _frame: setattr(runtime, "stop_requested", True)
            )
        runtime.sample("preflight")
        record = None
        if stage in {"Q4_ORIGINAL", "Q5_NOTCH"}:
            # The conditional worker must not allocate a second p4/p6 stack
            # until the settled parent-owned predecessor has passed its own
            # evidence gate.
            predecessor = _v14_predecessor_gate(
                runtime,
                str(stage),
                resolved_payload=resolved_payload,
            )
            if not predecessor.get("qualified"):
                record = {
                    "schema": f"task039extra.v14.{str(stage).lower()}.v2",
                    "stage": str(stage),
                    "status": f"{stage}_PREDECESSOR_NOT_QUALIFIED",
                    "official_result": False,
                    "stage_pass": False,
                    "result_classification": "PREDECESSOR_NOT_QUALIFIED",
                    "predecessor": predecessor,
                }
                runtime.marker(f"{str(stage).lower()}_predecessor_not_qualified", record)
            else:
                # Only the common-cache estimate is checked before common
                # construction.  The fresh volume estimate is checked after
                # the actual common objects are resident.
                _v14_known_preallocation_gate(
                    runtime,
                    str(stage),
                    include_common=True,
                    include_matrices=False,
                )
                cfg_common = _build_common(runtime, cfg)
                try:
                    _v14_known_preallocation_gate(
                        runtime,
                        str(stage),
                        include_common=False,
                        include_matrices=True,
                    )
                    record = _v14_q4_q5_fullspace(
                        runtime,
                        cfg_common,
                        resolved_payload,
                        stage=str(stage),
                        predecessor=predecessor,
                    )
                finally:
                    runtime.set_phase("cleanup")
                    _destroy_common(cfg_common, runtime)
                    runtime.sample("post_common_cleanup")
        elif stage == "Q6_FINALIZE":
            record = _q6_finalize(runtime)
            runtime.set_phase("cleanup")
            runtime.sample("q6_finalize_cleanup")
        else:
            if stage in {
                "Q0_CORE",
                "Q1_FULL_DIRECT",
                "Q2_SCHUR_DIRECT",
                "Q3_INTERFACE_CONTROL",
            }:
                # Only the common-cache estimate is checked before
                # construction.  The matrix estimate is deferred until the
                # actual common core (and reviewed RHS packets where needed)
                # is resident immediately before volume allocation.
                _v14_known_preallocation_gate(
                    runtime,
                    str(stage),
                    include_common=True,
                    include_matrices=False,
                )
            cfg_common = _build_common(runtime, cfg)
            try:
                if stage == "Q0_CORE":
                    _v14_known_preallocation_gate(
                        runtime,
                        str(stage),
                        include_common=False,
                        include_matrices=True,
                    )
                    record = _q0_core(runtime, cfg_common)
                elif stage in {"Q1_FULL_DIRECT", "Q2_SCHUR_DIRECT"}:
                    rhs_records = _prepare_reviewed_rhs(
                        runtime,
                        cfg_common,
                        resolved_payload,
                        root,
                        53084,
                    )
                    _v14_known_preallocation_gate(
                        runtime,
                        str(stage),
                        include_common=False,
                        include_matrices=True,
                    )
                    if stage == "Q1_FULL_DIRECT":
                        record = _q1_full_direct(runtime, cfg_common, rhs_records)
                    else:
                        record = _q2_schur_direct(runtime, cfg_common, rhs_records)
                elif stage == "Q3_INTERFACE_CONTROL":
                    rhs_records = _prepare_reviewed_rhs(
                        runtime,
                        cfg_common,
                        resolved_payload,
                        root,
                        53084,
                    )
                    _v14_known_preallocation_gate(
                        runtime,
                        str(stage),
                        include_common=False,
                        include_matrices=True,
                    )
                    record = _q3_interface_control(
                        runtime,
                        cfg_common,
                        rhs_records,
                        resolved_payload,
                    )
                else:
                    raise ValueError(f"unsupported V14 stage {stage!r}")
            finally:
                _release_reviewed_rhs(rhs_records)
                runtime.set_phase("cleanup")
                _destroy_common(cfg_common, runtime)
                runtime.sample("post_common_cleanup")
        summary.update(record)
        summary.update(runtime.time_policy_facts)
        summary["status"] = record["status"]
        summary["official_result"] = bool(record.get("official_result", False))
        summary["stage_pass"] = bool(
            record.get("stage_pass", summary["official_result"])
        )
        if "admission_pass" in record:
            summary["admission_pass"] = bool(record["admission_pass"])
        summary["result_classification"] = record.get(
            "result_classification",
            "DISCRETE_SOLVER_OUTPUT_PASS"
            if summary["official_result"]
            else record.get("status", "NOT_RUN"),
        )
    except V14ResourceStop as exc:
        summary.update(
            status="CONTROLLED_STOP",
            official_result=False,
            stage_pass=False,
            result_classification=exc.classification,
            error=str(exc),
        )
    except Exception as exc:
        summary.update(
            status="FAILED",
            official_result=False,
            stage_pass=False,
            result_classification="WORKER_FAILED",
            error={"type": type(exc).__name__, "message": str(exc)},
        )
    finally:
        for signum, handler in handlers.items():
            signal.signal(signum, handler)
        _write_json(directory / "physical_p4_schur_v14_summary.json", summary)
        if runtime is not None:
            runtime.marker("v14_worker_complete", summary)
    return {
        "passed": bool(summary.get("stage_pass", summary.get("official_result"))),
        "errors": []
        if summary.get("stage_pass", summary.get("official_result"))
        else [str(summary.get("error", summary.get("status", "V14 stage did not pass")))],
        "summary": summary,
        "numerical_output_directory": str(directory / "numerical_output"),
    }


__all__ = ["run_physical_p4_schur_v14"]
