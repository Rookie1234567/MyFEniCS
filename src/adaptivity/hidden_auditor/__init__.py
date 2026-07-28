"""Evaluator-only final hidden audit for Task035e.

The blind controller must not import this package.  The only high-level entry
point consumes a fully frozen JSON bundle and emits one terminal audit.
"""

from .api import (
    HiddenAuditExecution,
    HiddenAuditWriteReceipt,
    audit_frozen_candidate,
    build_hidden_audit_payload,
    validate_hidden_audit_payload,
    write_hidden_audit_payload,
)
from .audit import audit_candidate_against_reference
from .contracts import (
    CANDIDATE_BUNDLE_SCHEMA,
    CANDIDATE_OUTPUT_SCHEMA,
    FIXED_GOAL_IDS,
    FIXED_M,
    FIXED_N,
    FIXED_ORDER_KEYS,
    FIXED_PORTS,
    FORMAL_GOAL_IDS,
    FORMAL_GOAL_INVENTORY_SHA256,
    FORMAL_TOTAL_NAMES,
    FREEZE_RECEIPT_SCHEMA,
    HIDDEN_AUDIT_SCHEMA,
    TWO_PATH_GATE_SCHEMA,
    AuditGate,
    AuditItem,
    CandidateFreezeReceipt,
    HiddenAuditContractError,
    HiddenAuditReport,
    canonical_json_sha256,
)
from .package_reader import (
    CandidatePreflight,
    preflight_frozen_candidate,
    read_qualified_reference_after_preflight,
)


__all__ = [
    "CANDIDATE_BUNDLE_SCHEMA",
    "CANDIDATE_OUTPUT_SCHEMA",
    "FIXED_GOAL_IDS",
    "FIXED_M",
    "FIXED_N",
    "FIXED_ORDER_KEYS",
    "FIXED_PORTS",
    "FORMAL_GOAL_IDS",
    "FORMAL_GOAL_INVENTORY_SHA256",
    "FORMAL_TOTAL_NAMES",
    "FREEZE_RECEIPT_SCHEMA",
    "HIDDEN_AUDIT_SCHEMA",
    "TWO_PATH_GATE_SCHEMA",
    "AuditGate",
    "AuditItem",
    "CandidateFreezeReceipt",
    "CandidatePreflight",
    "HiddenAuditContractError",
    "HiddenAuditExecution",
    "HiddenAuditReport",
    "HiddenAuditWriteReceipt",
    "audit_candidate_against_reference",
    "audit_frozen_candidate",
    "build_hidden_audit_payload",
    "canonical_json_sha256",
    "preflight_frozen_candidate",
    "read_qualified_reference_after_preflight",
    "validate_hidden_audit_payload",
    "write_hidden_audit_payload",
]
