"""Single-shot API and atomic terminal receipt for the hidden auditor."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping

from .audit import audit_candidate_against_reference
from .contracts import (
    EXPECTED_AMPLITUDE_OUTPUT_IDS,
    EXPECTED_FIELD_OUTPUT_IDS,
    EXPECTED_HARD_GATE_IDS,
    EXPECTED_POWER_OUTPUT_IDS,
    EXPECTED_TOTAL_OUTPUT_IDS,
    HIDDEN_AUDIT_SCHEMA,
    HiddenAuditContractError,
    HiddenAuditReport,
    canonical_json_sha256,
    exact_mapping,
    recompute_full_propagating_spectrum_gate,
    require_sha256,
)
from .package_reader import (
    preflight_frozen_candidate,
    read_qualified_reference_after_preflight,
)


_AUDIT_PAYLOAD_KEYS = frozenset(
    {
        "schema_version",
        "terminal",
        "status",
        "passed",
        "candidate_frozen_payload_sha256",
        "candidate_output_sha256",
        "reference_sealed_payload_sha256",
        "reference_campaign_binding_sha256",
        "counts",
        "items",
        "gates",
        "audit_payload_sha256",
    }
)
_AUDIT_ITEM_KEYS = frozenset(
    {
        "category",
        "output_id",
        "reference_value",
        "candidate_value",
        "actual_error",
        "tolerance",
        "reference_uncertainty",
        "applicable",
        "passed",
        "reason",
    }
)
_AUDIT_GATE_KEYS = frozenset({"gate_id", "actual", "limit", "passed", "reason"})
_COUNT_KEYS = frozenset(
    {
        "fixed_order_inventory",
        "power_passed",
        "power_total",
        "power_applicable",
        "amplitude_passed",
        "amplitude_total",
        "total_passed",
        "total_total",
        "field_passed",
        "field_total",
        "hard_gate_passed",
        "hard_gate_total",
    }
)


@dataclass(frozen=True, slots=True)
class HiddenAuditWriteReceipt:
    """Non-oracle receipt for one immutable terminal audit file."""

    path: Path
    audit_payload_sha256: str
    byte_count: int
    status: str
    passed: bool
    terminal: bool


@dataclass(frozen=True, slots=True)
class HiddenAuditExecution:
    """In-memory report plus optional atomically written receipt."""

    report: HiddenAuditReport
    write_receipt: HiddenAuditWriteReceipt | None


def build_hidden_audit_payload(
    report: HiddenAuditReport,
) -> dict[str, Any]:
    """Construct and self-verify one hash-bound pure-JSON audit payload."""

    if not isinstance(report, HiddenAuditReport):
        raise TypeError("report must use HiddenAuditReport")
    unsigned: dict[str, Any] = {
        "schema_version": HIDDEN_AUDIT_SCHEMA,
        "terminal": report.terminal,
        "status": report.status,
        "passed": report.passed,
        "candidate_frozen_payload_sha256": (
            report.candidate_frozen_payload_sha256
        ),
        "candidate_output_sha256": report.candidate_output_sha256,
        "reference_sealed_payload_sha256": (
            report.reference_sealed_payload_sha256
        ),
        "reference_campaign_binding_sha256": (
            report.reference_campaign_binding_sha256
        ),
        "counts": report.counts_payload(),
        "items": [item.as_payload() for item in report.items],
        "gates": [gate.as_payload() for gate in report.gates],
    }
    payload = {
        **unsigned,
        "audit_payload_sha256": canonical_json_sha256(unsigned),
    }
    validate_hidden_audit_payload(payload)
    return payload


def validate_hidden_audit_payload(payload: Mapping[str, Any]) -> None:
    """Fail closed if a terminal receipt was changed after the audit."""

    row = exact_mapping(payload, _AUDIT_PAYLOAD_KEYS, path="audit")
    if row["schema_version"] != HIDDEN_AUDIT_SCHEMA:
        raise HiddenAuditContractError("audit schema_version is unsupported")
    if row["terminal"] is not True:
        raise HiddenAuditContractError("hidden audit receipt must be terminal")
    if not isinstance(row["passed"], bool):
        raise HiddenAuditContractError("audit.passed must be boolean")
    expected_status = (
        "REFERENCE_BLIND_HP_ACCURACY_PASS"
        if row["passed"]
        else "BLIND_STOP_FALSE_POSITIVE"
    )
    if row["status"] != expected_status:
        raise HiddenAuditContractError(
            "audit status disagrees with passed flag"
        )
    for name in (
        "candidate_frozen_payload_sha256",
        "candidate_output_sha256",
        "reference_sealed_payload_sha256",
        "reference_campaign_binding_sha256",
        "audit_payload_sha256",
    ):
        require_sha256(row[name], path=f"audit.{name}")
    if not isinstance(row["items"], list) or not isinstance(row["gates"], list):
        raise HiddenAuditContractError(
            "audit items and gates must be arrays"
        )
    if not isinstance(row["counts"], Mapping):
        raise HiddenAuditContractError("audit counts must be an object")
    expected_by_category = {
        "order_power": EXPECTED_POWER_OUTPUT_IDS,
        "order_amplitude": EXPECTED_AMPLITUDE_OUTPUT_IDS,
        "total": EXPECTED_TOTAL_OUTPUT_IDS,
        "field": EXPECTED_FIELD_OUTPUT_IDS,
    }
    for index, item in enumerate(row["items"]):
        item_row = exact_mapping(
            item,
            _AUDIT_ITEM_KEYS,
            path=f"audit.items[{index}]",
        )
        if not isinstance(item_row["passed"], bool) or not isinstance(
            item_row["applicable"],
            bool,
        ):
            raise HiddenAuditContractError(
                "audit item pass/applicability flags must be boolean"
            )
    for category, expected_ids in expected_by_category.items():
        observed_ids = [
            item["output_id"]
            for item in row["items"]
            if item["category"] == category
        ]
        if (
            len(observed_ids) != len(set(observed_ids))
            or set(observed_ids) != set(expected_ids)
        ):
            raise HiddenAuditContractError(
                f"audit {category} item inventory is incomplete"
            )
    if any(
        item["category"] not in expected_by_category for item in row["items"]
    ):
        raise HiddenAuditContractError(
            "audit contains an unsupported item category"
        )
    for index, gate in enumerate(row["gates"]):
        gate_row = exact_mapping(
            gate,
            _AUDIT_GATE_KEYS,
            path=f"audit.gates[{index}]",
        )
        if not isinstance(gate_row["passed"], bool):
            raise HiddenAuditContractError("audit gate passed must be boolean")
    gate_ids = [gate["gate_id"] for gate in row["gates"]]
    if (
        len(gate_ids) != len(set(gate_ids))
        or set(gate_ids) != set(EXPECTED_HARD_GATE_IDS)
    ):
        raise HiddenAuditContractError(
            "audit hard-gate inventory is incomplete"
        )
    spectrum_gate = next(
        gate
        for gate in row["gates"]
        if gate["gate_id"] == "full_propagating_spectrum_audit"
    )
    spectrum_recomputed = recompute_full_propagating_spectrum_gate(
        actual=spectrum_gate["actual"],
        limit=spectrum_gate["limit"],
    )
    if spectrum_gate["passed"] is not spectrum_recomputed:
        raise HiddenAuditContractError(
            "audit full-spectrum gate passed flag is not recomputable"
        )
    counts = exact_mapping(row["counts"], _COUNT_KEYS, path="audit.counts")
    recomputed_counts = {
        "fixed_order_inventory": 16,
        "power_passed": sum(
            item["passed"]
            for item in row["items"]
            if item["category"] == "order_power"
        ),
        "power_total": len(EXPECTED_POWER_OUTPUT_IDS),
        "power_applicable": sum(
            item["applicable"]
            for item in row["items"]
            if item["category"] == "order_power"
        ),
        "amplitude_passed": sum(
            item["passed"]
            for item in row["items"]
            if item["category"] == "order_amplitude"
        ),
        "amplitude_total": len(EXPECTED_AMPLITUDE_OUTPUT_IDS),
        "total_passed": sum(
            item["passed"]
            for item in row["items"]
            if item["category"] == "total"
        ),
        "total_total": len(EXPECTED_TOTAL_OUTPUT_IDS),
        "field_passed": sum(
            item["passed"]
            for item in row["items"]
            if item["category"] == "field"
        ),
        "field_total": len(EXPECTED_FIELD_OUTPUT_IDS),
        "hard_gate_passed": sum(gate["passed"] for gate in row["gates"]),
        "hard_gate_total": len(EXPECTED_HARD_GATE_IDS),
    }
    if dict(counts) != recomputed_counts:
        raise HiddenAuditContractError(
            "audit counts disagree with the closed item/gate inventory"
        )
    item_pass = all(
        isinstance(item, Mapping) and item.get("passed") is True
        for item in row["items"]
    )
    gate_pass = all(
        isinstance(gate, Mapping) and gate.get("passed") is True
        for gate in row["gates"]
    )
    if row["passed"] != (item_pass and gate_pass):
        raise HiddenAuditContractError(
            "audit passed flag disagrees with item/gate evidence"
        )
    unsigned = dict(row)
    observed = unsigned.pop("audit_payload_sha256")
    if canonical_json_sha256(unsigned) != observed:
        raise HiddenAuditContractError(
            "hidden audit payload SHA-256 mismatch"
        )


def write_hidden_audit_payload(
    path: Path | str,
    payload: Mapping[str, Any],
    *,
    overwrite: bool = False,
) -> HiddenAuditWriteReceipt:
    """Atomically persist one terminal mode-0600 audit authority."""

    if overwrite:
        raise HiddenAuditContractError(
            "formal hidden-audit receipts are immutable and cannot be overwritten"
        )
    validate_hidden_audit_payload(payload)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not overwrite:
        raise FileExistsError(
            f"refusing to overwrite hidden audit receipt: {destination}"
        )
    encoded = (
        json.dumps(
            payload,
            sort_keys=True,
            indent=2,
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )
    descriptor, temporary_name = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary_path, destination)
        temporary_path.unlink()
        directory_descriptor = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary_path.unlink(missing_ok=True)
        raise
    return HiddenAuditWriteReceipt(
        path=destination,
        audit_payload_sha256=str(payload["audit_payload_sha256"]),
        byte_count=len(encoded),
        status=str(payload["status"]),
        passed=bool(payload["passed"]),
        terminal=True,
    )


def _claim_one_shot_audit(
    *,
    sealed_reference_path: Path,
    frozen_payload_sha256: str,
    audit_receipt_path: Path,
) -> Path:
    """Persist an exclusive consumed marker before hidden data is opened."""

    claim = sealed_reference_path.with_name(
        f".{sealed_reference_path.name}.audit-{frozen_payload_sha256}.consumed"
    )
    payload = {
        "schema_version": "task035e.hidden-audit-consumed-marker.v1",
        "candidate_frozen_payload_sha256": frozen_payload_sha256,
        "audit_receipt_name_sha256": canonical_json_sha256(
            {"name": audit_receipt_path.name}
        ),
    }
    encoded = (
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )
    try:
        descriptor = os.open(
            claim,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError as error:
        raise HiddenAuditContractError(
            "this frozen candidate has already consumed its one hidden audit"
        ) from error
    try:
        os.write(descriptor, encoded)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return claim


def audit_frozen_candidate(
    *,
    freeze_receipt: Mapping[str, Any],
    candidate_bundle: Mapping[str, Any],
    sealed_reference_path: Path | str,
    audit_receipt_path: Path | str,
    overwrite: bool = False,
) -> HiddenAuditExecution:
    """Perform exactly one final audit after all freeze checks have passed."""

    preflight = preflight_frozen_candidate(
        freeze_receipt,
        candidate_bundle,
    )
    if overwrite:
        raise HiddenAuditContractError(
            "formal hidden audit does not permit overwrite"
        )
    sealed_path = Path(sealed_reference_path)
    receipt_path = Path(audit_receipt_path)
    _claim_one_shot_audit(
        sealed_reference_path=sealed_path,
        frozen_payload_sha256=preflight.receipt.frozen_payload_sha256,
        audit_receipt_path=receipt_path,
    )
    package = read_qualified_reference_after_preflight(
        preflight,
        sealed_path,
    )
    report = audit_candidate_against_reference(preflight, package)
    write_receipt = write_hidden_audit_payload(
        receipt_path,
        build_hidden_audit_payload(report),
    )
    return HiddenAuditExecution(
        report=report,
        write_receipt=write_receipt,
    )


__all__ = [
    "HiddenAuditExecution",
    "HiddenAuditWriteReceipt",
    "audit_frozen_candidate",
    "build_hidden_audit_payload",
    "validate_hidden_audit_payload",
    "write_hidden_audit_payload",
]
