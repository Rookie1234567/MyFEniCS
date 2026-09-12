"""Task39extra V14 workers for the fresh p4 full/direct Schur comparison.

Q1 and Q2 are deliberately separate worker stages.  Each worker builds the
same p6/p4 mesh, mode inventory and three hash-bound p4 right-hand sides, then
exits after its own factors have been destroyed.  Q3--Q6 are explicit
not-run stages until the Q2 accuracy and memory decision authorizes them.
"""

from __future__ import annotations

import gc
import hashlib
import json
import os
from pathlib import Path
import signal
import time
from typing import Any, Mapping

import numpy as np

from src.io.physical_intermediate_profile import SCHUR_PROFILE, profile_facts


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


class V14ResourceStop(RuntimeError):
    """The worker-side stage inventory gate requested a controlled stop."""


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
    ) -> None:
        self.directory = directory
        self.stage = stage
        self.contract = contract
        self.root = root
        self.source_sha = source_sha
        self.events_path = directory / "v14_events.jsonl"
        self.resources_path = directory / "v14_worker_resources.jsonl"
        self.inventory_path = directory / "v14_inventory.json"
        self.phase_path = Path(
            os.environ.get("PHYSICAL_WATCHDOG_PHASE_PATH", directory / "workflow_phase.json")
        )
        self.parent_pid = int(os.environ.get("PHYSICAL_WATCHDOG_PARENT_PID", "-1"))
        self.parent_cap = int(
            os.environ.get(
                "PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES",
                contract["resources"]["tree_cap_bytes"],
            )
        )
        self.inventory_cap = contract["resources"]["inventory_memory_cap_bytes_by_stage"].get(stage)
        self.workspace_cap = int(
            contract["resources"]["shared_temp_workspace_cap_bytes"]
        )
        self.stop_requested = False
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
        if shared_ledger.get("batch_identity") != "review_v14":
            raise RuntimeError("V14 parent ledger batch identity changed")
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
                "schema": "task039extra.v14.inventory-ledger.v1",
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
        if projected > self.workspace_cap:
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
        if projected > self.workspace_cap:
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
        untouched_workspace = max(
            0, self.workspace_cap - workspace_live - workspace
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
                "rss_includes_live_workspace_plus_new_workspace_plus_"
                "untouched_shared_workspace_reserve"
            ),
            "survival_assumption": (
                "all currently reserved workspace is resident in sampled RSS; "
                "the unmaterialized remainder may appear with the next allocation"
            ),
        }
        self.marker("v14_projected_allocation_gate", facts)
        if projected_rss >= int(resource["launch_cap_bytes"]):
            raise V14ResourceStop(f"V14 projected resident allocation exceeds cap: {facts}")
        return facts

    def set_phase(self, phase: str) -> None:
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
        }
        _write_json(self.phase_path, value)

    def marker(self, name: str, facts: Mapping[str, Any] | None = None) -> None:
        if name.endswith("started") or name.endswith("_started"):
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

    def sample(self, label: str | None = None) -> dict[str, Any]:
        if self.stop_requested:
            raise V14ResourceStop("parent requested a V14 worker stop")
        if self.parent_pid <= 0 or self.parent_pid == os.getpid() or not Path(
            f"/proc/{self.parent_pid}"
        ).is_dir():
            raise RuntimeError("V14 worker requires the dedicated parent watchdog")
        from benchmarks.subreaper_watchdog import memory_envelope
        from benchmarks.task038_full3d_jit_staging import process_tree_snapshot

        value = process_tree_snapshot(self.parent_pid, self._phase, None)
        envelope = memory_envelope()
        dynamic_cap = (
            int(value["rss_bytes"])
            + int(envelope["effective_available_bytes"])
            - int(envelope["reserve_bytes"])
        )
        cap = min(self.parent_cap, dynamic_cap)
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
                "cap_policy": "min(parent_tree_cap,current_tree_rss+available-reserve)",
                "inventory_policy": "independent_live_matrix_factor_coupling_workspace_sum",
            }
        )
        _append_jsonl(self.resources_path, value)
        if (
            not value["all_status_readable"]
            or int(value["swap_bytes"]) != 0
            or int(envelope["effective_available_bytes"]) < int(envelope["reserve_bytes"])
            or int(value["rss_bytes"]) >= cap
            or (
                self.inventory_cap is not None
                and self.inventory_used_bytes > int(self.inventory_cap)
            )
            or self.workspace_live_bytes > self.workspace_cap
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
    if stage == "Q1_FULL_DIRECT":
        pair_upper = volume_payload + augmented_payload + 128 * 1024**2
        runtime.check_projected(
            "q1_original_volume_and_augmented_preallocation", pair_upper
        )
        runtime.marker(
            "q1_original_sparse_preallocation_gate",
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


def _build_common(runtime: _V14Runtime, cfg: Any) -> dict[str, Any]:
    from mpi4py import MPI
    from src.solvers.fullspace_physical_intermediate_runtime import (
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

    runtime.set_phase("setup")
    runtime.marker("v14_common_setup_started", {"levels": [6, 4]})
    levels = _build_same_mesh_levels(
        cfg, MPI.COMM_WORLD, (6, 4), include_positive_coefficients=True
    )
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
    p4 = build_same_mesh_physical_action(
        levels,
        cfg,
        4,
        mode_inventory=mode_inventory,
        volume_quadrature_metadata=quadrature,
    )
    runtime.sample("p4_physical_action")
    local_transfer = build_same_mesh_hcurl_transfer(6, 4)
    transfer = build_same_mesh_hcurl_owner_transfer(
        levels["spaces"][6],
        levels["floquets"][6],
        levels["spaces"][4],
        levels["floquets"][4],
        local_transfer=local_transfer,
    )
    runtime.marker("v14_p64_transfer_complete", dict(transfer=transfer.audit))
    metric = LosslessFEMetric(
        levels,
        6,
        cfg.k0,
        quadrature,
        build_cell_basis=False,
    )
    runtime.marker("v14_degree6_metric_complete", dict(metric=metric.audit))
    warm_p4 = _new_storage_vector(levels["spaces"][4])
    warm_p6 = None
    try:
        warm_p4.set(0)
        warm_p6 = transfer.apply_primal(warm_p4)
        metric.mass(np.zeros(metric.mass.indices.size, dtype=np.complex128))
        metric.curl(np.zeros(metric.curl.indices.size, dtype=np.complex128))
    finally:
        if warm_p6 is not None:
            warm_p6.destroy()
        warm_p4.destroy()
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
    common_inventory: dict[str, int] = {
        "p64_local_cache_bytes": required_int(
            transfer_audit, "local_cache_array_bytes", "P64 transfer audit"
        ),
        "p64_owner_plan_bytes": required_int(
            routing_costs, "plan_bytes", "P64 transfer routing audit"
        ),
        "p64_work_vector_bytes": int(
            16
            * (
                int(transfer_audit.get("fine_local_owned_rows", 0))
                + int(transfer_audit.get("coarse_local_owned_rows", 0))
            )
        ),
        "degree6_metric_vector_bytes": metric_vector_bytes,
    }
    for degree, bundle in ((6, fine), (4, p4)):
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
            "levels": sorted(int(value) for value in levels["spaces"]),
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
        "p4": p4,
        "cfg": cfg,
        "quadrature": quadrature,
        "integral_records": integral_records,
        "transfer": transfer,
        "local_transfer": local_transfer,
        "metric": metric,
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
    for name in ("p4", "fine"):
        bundle = common.pop(name, None)
        if bundle is not None:
            destroy_same_mesh_physical_action(bundle)
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
        missing = sorted(set(current_map) - set(reference_map))
        if missing or any(
            key not in reference_map or not np.array_equal(current_map[key], reference_map[key])
            for key in current_map
        ):
            raise ValueError(f"{item['stem']} fresh p4 native constraint map differs")
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
        for signum in (signal.SIGTERM, signal.SIGINT):
            handlers[signum] = signal.signal(
                signum, lambda _value, _frame: setattr(runtime, "stop_requested", True)
            )
        runtime.sample("preflight")
        if stage in {"Q0_CORE", "Q1_FULL_DIRECT", "Q2_SCHUR_DIRECT"}:
            # Only the common-cache estimate is checked before construction.
            # The Q1/Q2 matrix estimates are deliberately deferred until the
            # actual common core (and, for Q1/Q2, reviewed RHS packets) is
            # resident, immediately before volume allocation.
            _v14_known_preallocation_gate(
                runtime,
                str(stage),
                include_common=True,
                include_matrices=False,
            )
        if stage in {"Q3_INTERFACE_CONTROL", "Q4_ORIGINAL", "Q5_NOTCH", "Q6_FINALIZE"}:
            record = {
                "schema": f"task039extra.v14.{str(stage).lower()}.v1",
                "status": "NOT_RUN",
                "official_result": False,
                "result_classification": "controlled_not_run_pending_Q2_accuracy_and_memory_decision",
                "reason": "Review V14 requires Q2 to authorize the conditional later stages",
            }
        else:
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
                else:
                    raise ValueError(f"unsupported V14 stage {stage!r}")
            finally:
                _release_reviewed_rhs(rhs_records)
                runtime.set_phase("cleanup")
                _destroy_common(cfg_common, runtime)
                runtime.sample("post_common_cleanup")
        summary.update(record)
        summary["status"] = record["status"]
        summary["official_result"] = bool(record.get("official_result", False))
        summary["result_classification"] = (
            "DISCRETE_SOLVER_OUTPUT_PASS"
            if summary["official_result"]
            else record.get("status", "NOT_RUN")
        )
    except V14ResourceStop as exc:
        summary.update(
            status="CONTROLLED_STOP",
            official_result=False,
            result_classification="RESOURCE_CONTROLLED_STOP",
            error=str(exc),
        )
    except Exception as exc:
        summary.update(
            status="FAILED",
            official_result=False,
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
        "passed": bool(summary.get("official_result")),
        "errors": []
        if summary.get("official_result")
        else [str(summary.get("error", summary.get("status", "V14 stage did not pass")))],
        "summary": summary,
        "numerical_output_directory": str(directory / "numerical_output"),
    }


__all__ = ["run_physical_p4_schur_v14"]
