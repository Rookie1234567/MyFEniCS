"""Immutable V10 campaign-window loading and conservative budget helpers."""

from __future__ import annotations

from dataclasses import dataclass
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
from typing import Any, Mapping

from .workflow_timebase import (
    CONSERVATIVE_REALTIME,
    TimebaseInconsistency,
    checked_interval,
    clock_sample,
)


TASK40_V10_CAMPAIGN_WINDOW = (
    Path("benchmarks/artifacts/task40extra_0p7nm_engineering/local_w10_wsl")
    / "campaign_window.json"
)
CAMPAIGN_SCHEMA = "task40extra.review_v10_campaign.v1"
CAMPAIGN_SECONDS = 86_400.0
CLOSEOUT_RESERVE_SECONDS = 600.0
CAMPAIGN_ACCOUNTING_NAME = "campaign_accounting_v10.jsonl"
TASK40_V22_CAMPAIGN_WINDOW = (
    Path("benchmarks/artifacts/task40extra_0p7nm_engineering/local_v22_wsl")
    / "campaign_window_v22.json"
)
TASK40_V22_CAMPAIGN_SHA256 = "a4da3d83c2a06672a2337a518dcc8a8bb5d12a446e995783e0f9dd406427d777"
TASK40_V22_CAMPAIGN_SECONDS = 21_600.0
TASK40_V22_CLOSEOUT_RESERVE_SECONDS = 600.0
TASK40_V22_CAMPAIGN_ID = "task40extra_v22_generated_production_operator"
TASK40_V22_REVIEW_SHA = "c2ec1e87cbbc88ba568537d6d1d591d76794611e"
TASK40_V22_REVIEW_PATH = "docs/task40extra_0p7nm_engineering/review_report_v22.md"
TASK40_V22_STAGE_SCOPE = (
    "implementation",
    "targeted_tests",
    "geometry_descriptor",
    "local_port_components",
    "target_operator_probe",
    "bounded_q_tiles",
    "checker",
    "persistence_readback",
    "closeout",
)
TASK40_V22_FORBIDDEN_SCOPE = (
    "all_target_q_csr",
    "target_global_factor",
    "target_ksp",
    "full_target_field",
)
TASK40_V22_PARENT_WINDOW = {
    "path": "benchmarks/artifacts/task40extra_0p7nm_engineering/local_w19_wsl/campaign_window_v19.json",
    "sha256": "b1591b7cf03b79aaf0820d352e636bdb79a6800bb19489eba92375cb73cbe6b0",
    "t0_utc": "2026-10-09T01:45:00.727771902Z",
    "deadline_utc": "2026-10-10T01:45:00.727771902Z",
    "verified_expired": True,
}
TASK40_V22_PARENT_LEDGER = {
    "path": "benchmarks/artifacts/task40extra_0p7nm_engineering/local_w19_wsl/campaign_accounting_v10.jsonl",
    "sha256": "7ea9e880520accf2fd87d8ee63b894c7e3e1ec366308dd0c8bb4492abd705a11",
    "last_persisted_cumulative_seconds": 66919.72841801553,
    "unsettled_interval": "UNKNOWN_RETAINED_UNMODIFIED",
    "historical_cleanup": "UNKNOWN_RETAINED_UNMODIFIED",
}
TASK40_V23_CAMPAIGN_WINDOW = (
    Path("benchmarks/artifacts/task40extra_0p7nm_engineering/local_v23_wsl")
    / "campaign_window_v23.json"
)
TASK40_V23_CAMPAIGN_SHA256 = "e77793e53542c6094da819456457910893b33c9be5ca3b548482be6bfc3dbdfb"
TASK40_V23_CAMPAIGN_RECEIPT_SHA256 = "602cb1a4be5732ec2179e797ad0a01b1d7e799d57c71b139cc190dee0c9f23a9"
TASK40_V23_CAMPAIGN_SECONDS = 21_600.0
TASK40_V23_CLOSEOUT_RESERVE_SECONDS = 1_200.0
TASK40_V23_CAMPAIGN_ID = "task40extra_v23_compact_boundary_support_and_q_tiles"
TASK40_V23_REVIEW_COMMIT = "32a7293233985083ae5024b275b39fbdc7c56ab2"
TASK40_V23_REVIEW_SHA256 = "e0e27d5f2a533af54eebe80b314de95fa8bdd99da71694c46c478691ba6b35b5"
TASK40_V23_REVIEW_PATH = "docs/task40extra_0p7nm_engineering/review_report_v23.md"
TASK40_V23_SOURCE_AT_ENTRY = "084270e06f7a2c4d4e540ed839c7584d82fe32af"
TASK40_V23_STAGE_SCOPE = (
    "implementation",
    "targeted_tests",
    "geometry_descriptor",
    "compact_boundary_components",
    "target_operator_probe",
    "production_support_inventory",
    "bounded_global_direct_provider",
    "bounded_q_tiles",
    "filled_reference_q_tiles",
    "checker",
    "persistence_readback",
    "closeout",
)
TASK40_V23_FORBIDDEN_SCOPE = (
    "all_target_q_csr",
    "target_global_factor",
    "target_symbolic",
    "target_numeric",
    "target_ksp",
    "full_target_field",
)
TASK40_V23_PARENT_WINDOW = {
    "path": "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v22_wsl/campaign_window_v22.json",
    "sha256": "a4da3d83c2a06672a2337a518dcc8a8bb5d12a446e995783e0f9dd406427d777",
    "t0_utc": "2026-10-10T02:34:32Z",
    "deadline_utc": "2026-10-10T08:34:32Z",
    "verified_expired": True,
}
TASK40_V23_PARENT_LEDGER = {
    "path": "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v22_wsl/campaign_accounting_v10.jsonl",
    "sha256": "9b4ed57a47eeff0caec1b522af325ff331d86cd42a0495d1a359aa894e78dca0",
    "last_sequence": 16089,
    "last_label": "controller_after_commit_push_readback",
    "last_persisted_cumulative_seconds": 21607.787895350273,
    "unsettled_interval": "UNKNOWN_RETAINED_UNMODIFIED",
    "historical_cleanup": "worker native/temp UNKNOWN; external V22 descendants cleared; scopes preserved",
}
TASK40_V24_CAMPAIGN_WINDOW = (
    Path("benchmarks/artifacts/task40extra_0p7nm_engineering/local_v24_wsl")
    / "campaign_window_v24.json"
)
TASK40_V24_CAMPAIGN_SHA256 = "b6a3063404fdbfd88c1099f381c9fe64c09f9bf04e7e7a3871e5454dfa728358"
TASK40_V24_CAMPAIGN_RECEIPT = (
    Path("benchmarks/artifacts/task40extra_0p7nm_engineering/local_v24_wsl")
    / "registration_receipt_v24.json"
)
TASK40_V24_CAMPAIGN_RECEIPT_SHA256 = "32fd8cce122e391c6bcc7671ecfb9cc99b33b40d31e903a849676aece3bdfc76"
TASK40_V24_CAMPAIGN_SECONDS = 21_600.0
TASK40_V24_CLOSEOUT_RESERVE_SECONDS = 1_200.0
TASK40_V24_CAMPAIGN_ID = "task40extra_v24_real_q_port_reuse_volume_and_row_tiles"
TASK40_V24_REVIEW_COMMIT = "92a59c167b53f828cc0408eca664d0eebc878428"
TASK40_V24_REVIEW_SHA256 = "92393f51aacbff9fc9f4c322b213666fe9869b6890ee9913748a45af2d226786"
TASK40_V24_REVIEW_PATH = "docs/task40extra_0p7nm_engineering/review_report_v24.md"
TASK40_V24_SOURCE_AT_ENTRY = "84dce5a39eb34a259166f34e063312a2cd86ef0c"
TASK40_V24_STAGE_SCOPE = (
    "implementation",
    "targeted_tests",
    "target_operator_probe",
    "bounded_q_tiles",
    "filled_reference_q_tiles",
    "bounded_port_mode_reuse",
    "bounded_global_direct_provider",
    "production_volume_classes",
    "bounded_volume_action",
    "volume_panel",
    "v17_row_tile",
    "selected_reference_q_build_only_conditional",
    "checker",
    "persistence_readback",
    "closeout",
)
TASK40_V24_FORBIDDEN_SCOPE = (
    "all_target_q_csr",
    "all_reference_q_csr",
    "target_global_factor",
    "target_symbolic",
    "target_numeric",
    "target_ksp",
    "full_target_field",
    "global_mumps_factor",
)
TASK40_V24_PARENT_WINDOW = {
    "path": "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v23_wsl/campaign_window_v23.json",
    "sha256": TASK40_V23_CAMPAIGN_SHA256,
    "t0_utc": "2026-10-10T09:00:51Z",
    "deadline_utc": "2026-10-10T15:00:51Z",
    "verified_expired": True,
}
TASK40_V24_PARENT_LEDGER = {
    "path": "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v23_wsl/campaign_accounting_v10.jsonl",
    "sha256": "2892d305b53f01229b976f925591ccbafd0bf4fc87a1ac823a263e021977322b",
    "last_sequence": 34909,
    "last_label": "controller_committed_pushed_remote_readback_administrative_closeout_no_numerical_work",
    "last_persisted_cumulative_seconds": 22012.362380510654,
    "unsettled_interval": "UNKNOWN_RETAINED_UNMODIFIED",
    "administrative_closeout_overrun_preserved": True,
}
TASK40_V25_CAMPAIGN_WINDOW = (
    Path("benchmarks/artifacts/task40extra_0p7nm_engineering/local_v25_wsl")
    / "campaign_window_v25.json"
)
TASK40_V25_CAMPAIGN_SHA256 = "a8ee7ab9970ece892d85f9313180438e88561f0bfc63b68acdb11f536400def7"
TASK40_V25_CAMPAIGN_RECEIPT = (
    Path("benchmarks/artifacts/task40extra_0p7nm_engineering/local_v25_wsl")
    / "registration_receipt_v25.json"
)
TASK40_V25_CAMPAIGN_RECEIPT_SHA256 = "7918bfb1885597227adbdfe344ac5be7891d22bacfb4be4f613d2b6b2b7b7fab"
TASK40_V25_CAMPAIGN_SECONDS = 21_600.0
TASK40_V25_CLOSEOUT_RESERVE_SECONDS = 1_200.0
TASK40_V25_CAMPAIGN_ID = "task40extra_v25_complete_target_volume_and_selected_reference_q"
TASK40_V25_REVIEW_COMMIT = "4a524251339e00ad481b29af61df4f4625ed2581"
TASK40_V25_REVIEW_SHA256 = "087e6c80512418a0f71ccff83ad5c792b58b05a3f93adef59ec791d5bef5520e"
TASK40_V25_REVIEW_PATH = "docs/task40extra_0p7nm_engineering/review_report_v25.md"
TASK40_V25_SOURCE_AT_ENTRY = "c1a77d362d852d864668dcf5d43957880a6788df"
TASK40_V25_STAGE_SCOPE = (
    "implementation",
    "targeted_tests",
    "maps_owner_capacity",
    "target_operator_probe",
    "complete_target_volume_action",
    "selected_reference_q_consumer",
    "selected_reference_q_build_only",
    "selected_reference_q_csr",
    "reference_port_generation_projection",
    "checker",
    "persistence_readback",
    "closeout",
)
TASK40_V25_FORBIDDEN_SCOPE = (
    "all_target_q_csr",
    "all_reference_q_csr",
    "global_mumps_factor",
    "target_symbolic",
    "target_numeric",
    "target_ksp",
    "full_target_field",
)
TASK40_V25_PARENT_WINDOW = {
    "path": "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v24_wsl/campaign_window_v24.json",
    "sha256": TASK40_V24_CAMPAIGN_SHA256,
    "t0_utc": "2026-10-10T16:33:11Z",
    "deadline_utc": "2026-10-10T22:33:11Z",
    "verified_expired": True,
}
TASK40_V25_PARENT_LEDGER = {
    "path": "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v24_wsl/campaign_accounting_v10.jsonl",
    "sha256": "b8ac409260e344741f9f5a135f1a64ca217631a38f52e2224f2ea5f9ea968faa",
    "last_sequence": 942,
    "last_label": "main_v24_final_remote_publication_verified",
    "last_persisted_cumulative_seconds": 16792.57081382109,
    "unsettled_interval": "UNKNOWN_RETAINED_UNMODIFIED",
}
TASK40_V26_CAMPAIGN_WINDOW = (
    Path("benchmarks/artifacts/task40extra_0p7nm_engineering/local_v26_wsl")
    / "campaign_window_v26.json"
)
TASK40_V26_CAMPAIGN_SHA256 = "ac533aaf3946c82fde961c77f002ff1b1b2a61401f2153507ff9462d472bc7f5"
TASK40_V26_CAMPAIGN_RECEIPT = (
    Path("benchmarks/artifacts/task40extra_0p7nm_engineering/local_v26_wsl")
    / "registration_receipt_v26.json"
)
TASK40_V26_CAMPAIGN_RECEIPT_SHA256 = "c8d0bb968bab7d2a8b63251b9005e6956aa4d841aaac2fe7f95f9db80562fec6"
TASK40_V26_CAMPAIGN_SECONDS = 21_600.0
TASK40_V26_CLOSEOUT_RESERVE_SECONDS = 1_200.0
TASK40_V26_CAMPAIGN_ID = "task40extra_v26_saved_reference_q_consumer_and_selected_q0_cost"
TASK40_V26_REVIEW_COMMIT = "83c4fed6e29ea19f0a70a92a403b867851f3ef35"
TASK40_V26_REVIEW_SHA256 = "d5dd227065395e621f5e8101896d18a63c5258d4b32f109aaef9bd511c945832"
TASK40_V26_REVIEW_PATH = "docs/task40extra_0p7nm_engineering/review_report_v26.md"
TASK40_V26_SOURCE_AT_ENTRY = "d9bde16eaede7a85e72d9e16f786a4e1ae7a3ed7"
TASK40_V26_STAGE_SCOPE = (
    "implementation",
    "targeted_tests",
    "saved_stream_replay",
    "native_reference_consumer",
    "complete_q0_row_counts",
    "complete_q0_csr",
    "selected_q0_factor_lifecycle",
    "checker",
    "persistence_readback",
    "closeout",
)
TASK40_V26_FORBIDDEN_SCOPE = (
    "rebuild_target_volume",
    "all_target_q_csr",
    "all_reference_q_csr",
    "all_q_factor",
    "target_symbolic",
    "target_numeric",
    "target_ksp",
    "full_target_field",
    "target_pde",
    "official_R_T_A",
)
TASK40_V26_PARENT_WINDOW = {
    "path": "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v25_wsl/campaign_window_v25.json",
    "sha256": TASK40_V25_CAMPAIGN_SHA256,
    "t0_utc": "2026-10-11T00:38:41Z",
    "deadline_utc": "2026-10-11T06:38:41Z",
    "verified_expired": True,
}
TASK40_V26_PARENT_LEDGER = {
    "path": "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v25_wsl/main_final_closeout_receipt_v25.json",
    "sha256": "cfc54b559c1ab9ba328d44e5ac322009d429a6951ac7b42a4b9a296d120cc8ae",
    "last_sequence": 14618,
    "last_label": "controller_push_readback_and_closeout_completed",
    "last_persisted_cumulative_seconds": 21322.0620501302,
    "unsettled_interval": "UNKNOWN_RETAINED_UNMODIFIED",
    "append_only_prefix": {
        "path": "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v25_wsl/campaign_accounting_v25_controller_closeout_prefix.jsonl",
        "bytes": 16875657,
        "sha256": "fcfc08881b123a80961c7fe7704af5f9f6c46f3939475a56d9976edc9b7bf972",
    },
}
TASK40_V27_CAMPAIGN_WINDOW = (
    Path("benchmarks/artifacts/task40extra_0p7nm_engineering/local_v27_wsl")
    / "campaign_window_v27.json"
)
TASK40_V27_CAMPAIGN_SHA256 = "e806c514c8208ae7a887bdb6ddaaec25936c9204a3ccc34a4fb870ad0bb0010d"
TASK40_V27_CAMPAIGN_RECEIPT = (
    Path("benchmarks/artifacts/task40extra_0p7nm_engineering/local_v27_wsl")
    / "registration_receipt_v27.json"
)
TASK40_V27_CAMPAIGN_RECEIPT_SHA256 = "fd34780d5aebf1db0dc09ecc28b900be7030e3661de577195d1cfe92482e5f7a"
TASK40_V27_CAMPAIGN_SECONDS = 21_600.0
TASK40_V27_CLOSEOUT_RESERVE_SECONDS = 1_200.0
TASK40_V27_CAMPAIGN_ID = "task40extra_v27_saved_only_complete_q0_csr_and_factor_handoff"
TASK40_V27_REVIEW_COMMIT = "06eb5ae5cdaaa6de0d4d805937a279f8d06e0351"
TASK40_V27_REVIEW_SHA256 = "d754abfc13bcea86d4a855707e59340ff449c6b6593e3b619f9cd74215dd5c69"
TASK40_V27_REVIEW_PATH = "docs/task40extra_0p7nm_engineering/review_report_v27.md"
TASK40_V27_SOURCE_AT_ENTRY = "399787abc991e0e30975bc694bd18a9a30c5470e"
TASK40_V27_STAGE_SCOPE = (
    "implementation",
    "targeted_tests",
    "readonly_v26_donor_import",
    "saved_only_q0_contributions",
    "lightweight_full_csr_preflight",
    "persistent_q0_structure",
    "complete_q0_numeric_csr",
    "csr_native_readback",
    "independent_csr_continuation",
    "selected_q0_factor_lifecycle",
    "checker",
    "persistence_readback",
    "handoff",
    "closeout",
)
TASK40_V27_FORBIDDEN_SCOPE = (
    "rebuild_target_volume",
    "rebuild_reference_fe_native",
    "rebuild_producer",
    "all_target_q_csr",
    "all_reference_q_csr",
    "all_q_factor",
    "target_ksp",
    "full_target_field",
    "target_pde",
    "official_R_T_A",
    "cross_host_execution",
)
TASK40_V27_PARENT_WINDOW = {
    "path": "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v26_wsl/campaign_window_v26.json",
    "sha256": "ac533aaf3946c82fde961c77f002ff1b1b2a61401f2153507ff9462d472bc7f5",
    "t0_utc": "2026-10-11T07:10:58Z",
    "deadline_utc": "2026-10-11T13:10:58Z",
    "verified_expired": True,
}
TASK40_V27_PARENT_LEDGER = {
    "path": "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v26_wsl/campaign_accounting_v10.jsonl",
    "sha256": "1ee33dcec8046c9343a0102ffb6ef9cdede8f885fb4d491c9a5e9ead635bf46e",
    "bytes": 19_600_105,
    "historical_cleanup": "V26 worker/checker descendants cleared; historical scopes retained separately",
    "last_sequence": 17_030,
    "last_label": "main_v26_commit_push_remote_readback_complete",
    "last_persisted_cumulative_seconds": 19_205.672001498642,
    "unsettled_interval": "UNKNOWN_RETAINED_UNMODIFIED",
}
TASK40_V28_CAMPAIGN_WINDOW = (
    Path("benchmarks/artifacts/task40extra_0p7nm_engineering/local_v28_wsl")
    / "campaign_window_v28.json"
)
TASK40_V28_CAMPAIGN_SHA256 = "dcefcfbf476f09b388554afc81a65ea85951d4d6162b6dad8743766e6742c9a0"
TASK40_V28_CAMPAIGN_RECEIPT = (
    Path("benchmarks/artifacts/task40extra_0p7nm_engineering/local_v28_wsl")
    / "registration_receipt_v28.json"
)
TASK40_V28_CAMPAIGN_RECEIPT_SHA256 = "e2f4b5673918c3c94981b0596359fd46406a78fd48e2743ee72375a42093a58e"
TASK40_V28_CAMPAIGN_SECONDS = 21_600.0
TASK40_V28_CLOSEOUT_RESERVE_SECONDS = 1_200.0
TASK40_V28_CAMPAIGN_ID = "task40extra_v28_sparse_q0_existing_manifest_continuation"
TASK40_V28_REVIEW_COMMIT = "b52c8d47a9db7f4e9d7f6d134a7f307b8728a4ab"
TASK40_V28_REVIEW_SHA256 = "320e5a7e3501d777c2291ca9f98cc7ac2331191e583225681e82f0de45d79275"
TASK40_V28_REVIEW_PATH = "docs/task40extra_0p7nm_engineering/review_report_v28.md"
TASK40_V28_SOURCE_AT_ENTRY = "b52c8d47a9db7f4e9d7f6d134a7f307b8728a4ab"
TASK40_V28_STAGE_SCOPE = (
    "implementation",
    "targeted_tests",
    "existing_manifest_continuation",
    "saved_q0_numeric_fill",
    "csr_native_readback",
    "single_q_factor_continuation",
    "checker",
    "persistence_readback",
    "handoff",
    "closeout",
)
TASK40_V28_FORBIDDEN_SCOPE = (
    "rebuild_target_volume",
    "rebuild_reference_fe_native",
    "rebuild_producer",
    "rebuild_routes_or_pattern",
    "all_target_q_csr",
    "all_q_factor",
    "target_ksp",
    "full_target_field",
    "target_pde",
    "official_R_T_A",
    "cross_host_execution",
    "ssh",
    "master_merge",
    "ordinary_solver_default_change",
)
TASK40_V28_PARENT_WINDOW = {
    "path": "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v27_wsl/campaign_window_v27.json",
    "sha256": TASK40_V27_CAMPAIGN_SHA256,
    "t0_utc": "2026-10-11T13:37:38Z",
    "deadline_utc": "2026-10-11T19:37:38Z",
    "verified_expired": True,
}
TASK40_V28_PARENT_LEDGER = {
    "path": "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v27_wsl/campaign_accounting_v10.jsonl",
    "sha256": "48b87396973a16d18da38b5e25fadd60ef5f2bffd65cf719e9126ce6409aa0db",
    "bytes": 52_838_711,
    "last_sequence": 45_735,
    "last_label": "main_v27_final_evidence_hash_audit",
    "last_persisted_cumulative_seconds": 21_990.37618080045,
    "unsettled_interval": "UNKNOWN_RETAINED_UNMODIFIED",
    "old_ledger_preserved": True,
}
TASK40_V29_CAMPAIGN_WINDOW = (
    Path("benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_wsl")
    / "campaign_window_v29.json"
)
TASK40_V29_CAMPAIGN_SECONDS = 21_600.0
TASK40_V29_CLOSEOUT_RESERVE_SECONDS = 1_200.0
TASK40_V29_CAMPAIGN_ID = "task40extra_v29_first_qualified_q0_factor_only"
TASK40_V29_REVIEW_COMMIT = "e85992c79d7e2b3f41cd1396ffb06edccdd93421"
TASK40_V29_REVIEW_SHA256 = "7a535053474bf864ed77dbf13f66aba1baf2172ff568738e10e2bc3d2266d51e"
TASK40_V29_REVIEW_PATH = "docs/task40extra_0p7nm_engineering/review_report_v29.md"
TASK40_V29_STAGE_SCOPE = (
    "authorized_target_preparation_and_dependency_import",
    "strict_existing_q0_factor_only",
    "conversion",
    "symbolic",
    "numeric",
    "fresh_nonzero_rhs_true_residual",
    "second_nonzero_rhs_repeated_solve",
    "evict_and_cleanup",
    "checker",
    "closeout",
)
TASK40_V29_FORBIDDEN_SCOPE = (
    "producer_FE_MPC_native_rebuild",
    "routes_pattern_fill_or_readback_rebuild",
    "all_q_factorization",
    "target_PDE_or_official_R_T_A",
    "automatic_cap_increase",
    "OOC_BLR_ordering_or_pivot_changes",
    "master_merge",
)
TASK40_V30_CAMPAIGN_WINDOW = (
    Path("benchmarks/artifacts/task40extra_0p7nm_engineering/local_v30_preparation")
    / "campaign_window_v30.json"
)
TASK40_V31_CAMPAIGN_WINDOW = (
    Path("benchmarks/artifacts/task40extra_0p7nm_engineering/local_v31_native")
    / "campaign_window_v31.json"
)
TASK40_V31_CAMPAIGN_SECONDS = 43_200.0
TASK40_V31_CLOSEOUT_RESERVE_SECONDS = 1_200.0
TASK40_V32_CAMPAIGN_SECONDS = 86_400.0
TASK40_V32_CLOSEOUT_RESERVE_SECONDS = 1_200.0
TASK40_V33_CAMPAIGN_SECONDS = 86_400.0
TASK40_V33_CLOSEOUT_RESERVE_SECONDS = 1_200.0
TASK40_V33_EXTENSION_TOTAL_SECONDS = 172_800.0
TASK40_V33_EXTENSION_NUMERIC_SECONDS = 171_600.0
TASK40_V33_EXTENSION_CLOSEOUT_SECONDS = 1_200.0
TASK40_V30_CAMPAIGN_SHA256 = "0730454198abcee55401331d74f24a667d0d52036f67e1be817a3426a8d381a7"
TASK40_V30_TARGET_CAMPAIGN_WINDOW = (
    Path("benchmarks/artifacts/task40extra_0p7nm_engineering/local_v30_wsl")
    / "campaign_window_v30.json"
)
TASK40_V30_TARGET_CAMPAIGN_SHA256 = "15ef0f6dd4221d71e488b2c2930ad1dd05328b06b0ce78819d8402093c1e8320"
TASK40_V30_TARGET_CLOCK_RECEIPT = (
    Path("benchmarks/artifacts/task40extra_0p7nm_engineering/local_v30_preparation")
    / "target_native_clock_receipt_v30.json"
)
TASK40_V30_TARGET_CLOCK_RECEIPT_SHA256 = "079a2031f16abe1d3eaf2a122801351670278d9007235b1705e0846e45920ae4"
TASK40_V30_ENTRY_RECEIPT = (
    Path("benchmarks/artifacts/task40extra_0p7nm_engineering/local_v30_preparation")
    / "controller_entry_receipt_v30.json"
)
TASK40_V30_ENTRY_RECEIPT_SHA256 = "6c24c32f951415e361276f027cc920b4ae940c5b1e135d7a9dc034ed28bf1756"
TASK40_V30_CAMPAIGN_SECONDS = 43_200.0
TASK40_V30_CLOSEOUT_RESERVE_SECONDS = 1_200.0
TASK40_V30_CAMPAIGN_ID = "task40extra_v30_all_q_reference_with_conditional_target_pilot"
TASK40_V30_REVIEW_COMMIT = "8c05f1bf2aecd318ca3270ddfb0b787dcc3465e8"
TASK40_V30_REVIEW_SHA256 = "d8fb7824c0a435b6528ab0c1132a0c86e2549dcf22441bfb88973f041f9f4d9e"
TASK40_V30_REVIEW_PATH = "docs/task40extra_0p7nm_engineering/review_report_v30.md"
TASK40_V30_SOURCE_AT_ENTRY = "8c05f1bf2aecd318ca3270ddfb0b787dcc3465e8"
TASK40_V30_STAGE_SCOPE = (
    "P0_contract_and_generic_entry",
    "P1_q4_csr_native",
    "P2_q1_q7_csr_native",
    "P3_all_q_resident_factor_bank",
    "P4_complete_reference_inverse",
    "P5_conditional_target_pilot",
    "P6_closeout",
)
TASK40_V30_FORBIDDEN_SCOPE = (
    "automatic_cap_increase",
    "window_refresh",
    "parameter_or_accuracy_scan",
    "MUMPS_or_ABI_change",
    "OOC_or_BLR",
    "unrelated_project_mutation",
    "master_merge",
)


def _utc_ns(value: Any) -> int:
    from calendar import timegm
    from datetime import datetime, timezone

    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("campaign timestamps must be explicit UTC ISO strings")
    whole, dot, fraction = value[:-1].partition(".")
    instant = datetime.strptime(whole, "%Y-%m-%dT%H:%M:%S").replace(
        tzinfo=timezone.utc
    )
    nanos = int((fraction + "000000000")[:9]) if dot else 0
    if dot and (not fraction.isdigit() or len(fraction) > 9):
        raise ValueError("campaign timestamp precision must not exceed nanoseconds")
    return timegm(instant.utctimetuple()) * 1_000_000_000 + nanos


def _validate_v22_campaign_registration(
    resolved: Path, digest: str, payload: Mapping[str, Any]
) -> None:
    expected_path = (
        Path(__file__).resolve().parents[2] / TASK40_V22_CAMPAIGN_WINDOW
    ).resolve()
    if resolved != expected_path:
        raise ValueError("the V22 campaign window is not at its registered path")
    if digest != TASK40_V22_CAMPAIGN_SHA256:
        raise ValueError("the registered V22 campaign window SHA-256 changed")
    expected_fields = {
        "schema": CAMPAIGN_SCHEMA,
        "campaign": TASK40_V22_CAMPAIGN_ID,
        "authority": "User-authorized Review V22 section 7: independent six-hour work package",
        "active_review_sha": TASK40_V22_REVIEW_SHA,
        "active_review_path": TASK40_V22_REVIEW_PATH,
        "source_at_entry": TASK40_V22_REVIEW_SHA,
        "t0_utc": "2026-10-10T02:34:32Z",
        "deadline_utc": "2026-10-10T08:34:32Z",
        "campaign_seconds": TASK40_V22_CAMPAIGN_SECONDS,
        "closeout_reserve_seconds": TASK40_V22_CLOSEOUT_RESERVE_SECONDS,
        "time_policy": CONSERVATIVE_REALTIME,
        "stage_scope": list(TASK40_V22_STAGE_SCOPE),
        "forbidden_scope": list(TASK40_V22_FORBIDDEN_SCOPE),
        "window_refreshed": False,
        "old_costs_and_unknowns_preserved": True,
        "parent_window": TASK40_V22_PARENT_WINDOW,
        "parent_ledger": TASK40_V22_PARENT_LEDGER,
    }
    changed = [
        key for key, value in expected_fields.items() if payload.get(key) != value
    ]
    if changed:
        raise ValueError(f"registered V22 campaign identity or scope changed: {changed}")


def _validate_v23_campaign_registration(
    resolved: Path, digest: str, payload: Mapping[str, Any]
) -> None:
    expected_path = (
        Path(__file__).resolve().parents[2] / TASK40_V23_CAMPAIGN_WINDOW
    ).resolve()
    if resolved != expected_path:
        raise ValueError("the V23 campaign window is not at its registered path")
    if digest != TASK40_V23_CAMPAIGN_SHA256:
        raise ValueError("the registered V23 campaign window SHA-256 changed")
    expected_fields = {
        "schema": CAMPAIGN_SCHEMA,
        "campaign": TASK40_V23_CAMPAIGN_ID,
        "authority": "User-authorized Review V23 section 8 independent six-hour package",
        "active_review_sha": TASK40_V23_REVIEW_COMMIT,
        "active_review_path": TASK40_V23_REVIEW_PATH,
        "active_review_sha256": TASK40_V23_REVIEW_SHA256,
        "source_at_entry": TASK40_V23_SOURCE_AT_ENTRY,
        "review_at_registration": TASK40_V23_REVIEW_COMMIT,
        "t0_utc": "2026-10-10T09:00:51Z",
        "deadline_utc": "2026-10-10T15:00:51Z",
        "campaign_seconds": TASK40_V23_CAMPAIGN_SECONDS,
        "closeout_reserve_seconds": TASK40_V23_CLOSEOUT_RESERVE_SECONDS,
        "time_policy": CONSERVATIVE_REALTIME,
        "stage_scope": list(TASK40_V23_STAGE_SCOPE),
        "forbidden_scope": list(TASK40_V23_FORBIDDEN_SCOPE),
        "window_refreshed": False,
        "old_costs_and_unknowns_preserved": True,
        "parent_window": TASK40_V23_PARENT_WINDOW,
        "parent_ledger": TASK40_V23_PARENT_LEDGER,
    }
    changed = [
        key for key, value in expected_fields.items() if payload.get(key) != value
    ]
    if changed:
        raise ValueError(f"registered V23 campaign identity or scope changed: {changed}")


def _validate_v24_campaign_registration(
    resolved: Path, digest: str, payload: Mapping[str, Any]
) -> None:
    expected_path = (
        Path(__file__).resolve().parents[2] / TASK40_V24_CAMPAIGN_WINDOW
    ).resolve()
    if resolved != expected_path:
        raise ValueError("the V24 campaign window is not at its registered path")
    if digest != TASK40_V24_CAMPAIGN_SHA256:
        raise ValueError("the registered V24 campaign window SHA-256 changed")
    expected_fields = {
        "schema": CAMPAIGN_SCHEMA,
        "campaign": TASK40_V24_CAMPAIGN_ID,
        "authority": "User-authorized Review V24 section 7 independent six-hour package",
        "active_review_sha": TASK40_V24_REVIEW_COMMIT,
        "active_review_path": TASK40_V24_REVIEW_PATH,
        "active_review_sha256": TASK40_V24_REVIEW_SHA256,
        "source_at_entry": TASK40_V24_SOURCE_AT_ENTRY,
        "review_at_registration": TASK40_V24_REVIEW_COMMIT,
        "t0_utc": "2026-10-10T16:33:11Z",
        "deadline_utc": "2026-10-10T22:33:11Z",
        "campaign_seconds": TASK40_V24_CAMPAIGN_SECONDS,
        "closeout_reserve_seconds": TASK40_V24_CLOSEOUT_RESERVE_SECONDS,
        "time_policy": CONSERVATIVE_REALTIME,
        "stage_scope": list(TASK40_V24_STAGE_SCOPE),
        "forbidden_scope": list(TASK40_V24_FORBIDDEN_SCOPE),
        "window_refreshed": False,
        "old_costs_and_unknowns_preserved": True,
        "parent_window": TASK40_V24_PARENT_WINDOW,
        "parent_ledger": TASK40_V24_PARENT_LEDGER,
        "artifact_execution_identity_separate": True,
    }
    changed = [
        key for key, value in expected_fields.items() if payload.get(key) != value
    ]
    if changed:
        raise ValueError(f"registered V24 campaign identity or scope changed: {changed}")


def _validate_v25_campaign_registration(
    resolved: Path, digest: str, payload: Mapping[str, Any]
) -> None:
    expected_path = (
        Path(__file__).resolve().parents[2] / TASK40_V25_CAMPAIGN_WINDOW
    ).resolve()
    if resolved != expected_path:
        raise ValueError("the V25 campaign window is not at its registered path")
    if digest != TASK40_V25_CAMPAIGN_SHA256:
        raise ValueError("the registered V25 campaign window SHA-256 changed")
    expected_fields = {
        "schema": CAMPAIGN_SCHEMA,
        "campaign": TASK40_V25_CAMPAIGN_ID,
        "authority": "User-authorized Review V25 sections 4,5,7 independent six-hour package",
        "active_review_sha": TASK40_V25_REVIEW_COMMIT,
        "active_review_path": TASK40_V25_REVIEW_PATH,
        "active_review_sha256": TASK40_V25_REVIEW_SHA256,
        "source_at_entry": TASK40_V25_SOURCE_AT_ENTRY,
        "review_at_registration": TASK40_V25_REVIEW_COMMIT,
        "t0_utc": "2026-10-11T00:38:41Z",
        "deadline_utc": "2026-10-11T06:38:41Z",
        "campaign_seconds": TASK40_V25_CAMPAIGN_SECONDS,
        "closeout_reserve_seconds": TASK40_V25_CLOSEOUT_RESERVE_SECONDS,
        "time_policy": CONSERVATIVE_REALTIME,
        "stage_scope": list(TASK40_V25_STAGE_SCOPE),
        "forbidden_scope": list(TASK40_V25_FORBIDDEN_SCOPE),
        "window_refreshed": False,
        "old_costs_and_unknowns_preserved": True,
        "parent_window": TASK40_V25_PARENT_WINDOW,
        "parent_ledger": TASK40_V25_PARENT_LEDGER,
        "artifact_execution_identity_separate": True,
    }
    changed = [
        key for key, value in expected_fields.items() if payload.get(key) != value
    ]
    if changed:
        raise ValueError(f"registered V25 campaign identity or scope changed: {changed}")


def _validate_v26_campaign_registration(
    resolved: Path, digest: str, payload: Mapping[str, Any]
) -> None:
    expected_path = (
        Path(__file__).resolve().parents[2] / TASK40_V26_CAMPAIGN_WINDOW
    ).resolve()
    if resolved != expected_path:
        raise ValueError("the V26 campaign window is not at its registered path")
    if digest != TASK40_V26_CAMPAIGN_SHA256:
        raise ValueError("the registered V26 campaign window SHA-256 changed")
    expected_fields = {
        "schema": CAMPAIGN_SCHEMA,
        "campaign": TASK40_V26_CAMPAIGN_ID,
        "authority": "User-authorized Review V26 sections 4,5,7 independent six-hour package",
        "active_review_sha": TASK40_V26_REVIEW_COMMIT,
        "active_review_path": TASK40_V26_REVIEW_PATH,
        "active_review_sha256": TASK40_V26_REVIEW_SHA256,
        "source_at_entry": TASK40_V26_SOURCE_AT_ENTRY,
        "review_at_registration": TASK40_V26_REVIEW_COMMIT,
        "t0_utc": "2026-10-11T07:10:58Z",
        "deadline_utc": "2026-10-11T13:10:58Z",
        "campaign_seconds": TASK40_V26_CAMPAIGN_SECONDS,
        "closeout_reserve_seconds": TASK40_V26_CLOSEOUT_RESERVE_SECONDS,
        "time_policy": CONSERVATIVE_REALTIME,
        "stage_scope": list(TASK40_V26_STAGE_SCOPE),
        "forbidden_scope": list(TASK40_V26_FORBIDDEN_SCOPE),
        "window_refreshed": False,
        "old_costs_and_unknowns_preserved": True,
        "parent_window": TASK40_V26_PARENT_WINDOW,
        "parent_ledger": TASK40_V26_PARENT_LEDGER,
        "artifact_execution_identity_separate": True,
        "numeric_scope": "Reuse V25 full target volume; saved q0/q4 replay, native consumer, full q0 structure/CSR, and conditionally one selected-q0 factor lifecycle.",
    }
    changed = [
        key for key, value in expected_fields.items() if payload.get(key) != value
    ]
    if changed:
        raise ValueError(f"registered V26 campaign identity or scope changed: {changed}")


def _validate_v27_campaign_registration(
    resolved: Path, digest: str, payload: Mapping[str, Any]
) -> None:
    expected_path = (
        Path(__file__).resolve().parents[2] / TASK40_V27_CAMPAIGN_WINDOW
    ).resolve()
    if resolved != expected_path:
        raise ValueError("the V27 campaign window is not at its registered path")
    if digest != TASK40_V27_CAMPAIGN_SHA256:
        raise ValueError("the registered V27 campaign window SHA-256 changed")
    expected_fields = {
        "schema": CAMPAIGN_SCHEMA,
        "campaign": TASK40_V27_CAMPAIGN_ID,
        "authority": "User-authorized Review V27 sections 3,4,6 independent six-hour saved-only CSR and single-q handoff package",
        "active_review_sha": TASK40_V27_REVIEW_COMMIT,
        "active_review_path": TASK40_V27_REVIEW_PATH,
        "active_review_sha256": TASK40_V27_REVIEW_SHA256,
        "source_at_entry": TASK40_V27_SOURCE_AT_ENTRY,
        "review_at_registration": TASK40_V27_REVIEW_COMMIT,
        "t0_utc": "2026-10-11T13:37:38Z",
        "deadline_utc": "2026-10-11T19:37:38Z",
        "campaign_seconds": TASK40_V27_CAMPAIGN_SECONDS,
        "closeout_reserve_seconds": TASK40_V27_CLOSEOUT_RESERVE_SECONDS,
        "time_policy": CONSERVATIVE_REALTIME,
        "stage_scope": list(TASK40_V27_STAGE_SCOPE),
        "forbidden_scope": list(TASK40_V27_FORBIDDEN_SCOPE),
        "window_refreshed": False,
        "old_costs_and_unknowns_preserved": True,
        "parent_window": TASK40_V27_PARENT_WINDOW,
        "parent_ledger": TASK40_V27_PARENT_LEDGER,
        "artifact_execution_identity_separate": True,
        "numeric_scope": "Readonly V26 donor import; saved-only complete q0 CSR without mesh/p6/MPC/JIT/native reconstruction; persistent structure/fill/readback; conditional existing selected-q0 factor lifecycle or explicit CSR_PENDING handoff.",
        "bootstrap_utc_elapsed_seconds": 362.311757244,
        "bootstrap_boottime_elapsed_seconds": 0.0,
        "bootstrap_time_treatment": "T0 frozen from first canonical preparation at 2026-10-11T13:37:38Z; 362.311757244 s UTC debit charged conservatively; pre-anchor monotonic interval UNKNOWN.",
    }
    changed = [
        key for key, value in expected_fields.items() if payload.get(key) != value
    ]
    if changed:
        raise ValueError(f"registered V27 campaign identity or scope changed: {changed}")


def _validate_v28_campaign_registration(
    resolved: Path, digest: str, payload: Mapping[str, Any]
) -> None:
    expected_path = (
        Path(__file__).resolve().parents[2] / TASK40_V28_CAMPAIGN_WINDOW
    ).resolve()
    if resolved != expected_path:
        raise ValueError("the V28 campaign window is not at its registered path")
    if digest != TASK40_V28_CAMPAIGN_SHA256:
        raise ValueError("the registered V28 campaign window SHA-256 changed")
    expected_fields = {
        "schema": CAMPAIGN_SCHEMA,
        "campaign": TASK40_V28_CAMPAIGN_ID,
        "authority": "User-authorized Review V28 existing-manifest q0 continuation package",
        "active_review_sha": TASK40_V28_REVIEW_COMMIT,
        "active_review_path": TASK40_V28_REVIEW_PATH,
        "active_review_sha256": TASK40_V28_REVIEW_SHA256,
        "source_at_entry": TASK40_V28_SOURCE_AT_ENTRY,
        "review_at_registration": TASK40_V28_REVIEW_COMMIT,
        "t0_utc": "2026-10-11T23:24:00Z",
        "deadline_utc": "2026-10-12T05:24:00Z",
        "campaign_seconds": TASK40_V28_CAMPAIGN_SECONDS,
        "closeout_reserve_seconds": TASK40_V28_CLOSEOUT_RESERVE_SECONDS,
        "time_policy": CONSERVATIVE_REALTIME,
        "stage_scope": list(TASK40_V28_STAGE_SCOPE),
        "forbidden_scope": list(TASK40_V28_FORBIDDEN_SCOPE),
        "window_refreshed": False,
        "old_costs_and_unknowns_preserved": True,
        "parent_window": TASK40_V28_PARENT_WINDOW,
        "parent_ledger": TASK40_V28_PARENT_LEDGER,
        "artifact_execution_identity_separate": True,
        "numeric_scope": (
            "Reuse V27 full q0 pattern and V26 donor arrays; exact sparse q0 numeric fill, "
            "four native CSR matvec readbacks, independent factor continuation only after "
            "qualification; no FE/native/producer/routes/pattern rebuild."
        ),
        "bootstrap_utc_elapsed_seconds": 324.654694973,
        "bootstrap_boottime_elapsed_seconds": 0.0,
        "bootstrap_time_treatment": (
            "T0 fixed at 2026-10-11T23:24:00Z; conservative UTC debit of "
            "324.654694973 s to the first qualified full clock sample; exact pre-anchor "
            "monotonic interval UNKNOWN; boottime field is a lower bound, not a measured zero."
        ),
    }
    changed = [
        key for key, value in expected_fields.items() if payload.get(key) != value
    ]
    if changed:
        raise ValueError(f"registered V28 campaign identity or scope changed: {changed}")


def _validate_v29_campaign_registration(
    resolved: Path, digest: str, payload: Mapping[str, Any]
) -> None:
    expected_path = (
        Path(__file__).resolve().parents[2] / TASK40_V29_CAMPAIGN_WINDOW
    ).resolve()
    if resolved != expected_path:
        raise ValueError("the V29 campaign window is not at its registered path")
    expected_fields = {
        "schema": CAMPAIGN_SCHEMA,
        "campaign": TASK40_V29_CAMPAIGN_ID,
        "authority": "User-authorized Review V29 first qualified q0 factor execution",
        "active_review_sha": TASK40_V29_REVIEW_COMMIT,
        "active_review_path": TASK40_V29_REVIEW_PATH,
        "active_review_sha256": TASK40_V29_REVIEW_SHA256,
        "review_at_registration": TASK40_V29_REVIEW_COMMIT,
        "campaign_seconds": TASK40_V29_CAMPAIGN_SECONDS,
        "closeout_reserve_seconds": TASK40_V29_CLOSEOUT_RESERVE_SECONDS,
        "time_policy": CONSERVATIVE_REALTIME,
        "stage_scope": list(TASK40_V29_STAGE_SCOPE),
        "forbidden_scope": list(TASK40_V29_FORBIDDEN_SCOPE),
        "window_refreshed": False,
        "old_costs_and_unknowns_preserved": True,
        "artifact_execution_identity_separate": True,
    }
    changed = [
        key for key, value in expected_fields.items() if payload.get(key) != value
    ]
    source_at_entry = payload.get("source_at_entry")
    if not isinstance(source_at_entry, str) or not re.fullmatch(
        r"[0-9a-f]{40,64}", source_at_entry
    ):
        changed.append("source_at_entry")
    approval = payload.get("user_approval")
    approval_sha = hashlib.sha256(
        json.dumps(
            approval, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    if not isinstance(approval, Mapping) or approval.get("scope") != "V29_Q0_FACTOR_ONLY":
        changed.append("user_approval_scope")
    if payload.get("user_approval_sha256") != approval_sha:
        changed.append("user_approval_sha256")
    if payload.get("t0_utc") == "2026-10-11T23:24:00Z":
        changed.append("t0_utc_reuses_v28")
    if changed:
        raise ValueError(f"registered V29 campaign identity or scope changed: {changed}")


def _validate_v30_campaign_registration(
    resolved: Path, digest: str, payload: Mapping[str, Any]
) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    control_window_path = (repo_root / TASK40_V30_CAMPAIGN_WINDOW).resolve()
    target_window_path = (repo_root / TASK40_V30_TARGET_CAMPAIGN_WINDOW).resolve()
    is_target_window = resolved == target_window_path
    if resolved not in {control_window_path, target_window_path}:
        raise ValueError("the V30 campaign window is not at a registered control or target path")
    expected_digest = (
        TASK40_V30_TARGET_CAMPAIGN_SHA256 if is_target_window else TASK40_V30_CAMPAIGN_SHA256
    )
    changed: list[str] = []
    if digest != expected_digest:
        changed.append("campaign_window_sha256")
    expected_fields = {
        "schema": CAMPAIGN_SCHEMA,
        "campaign": TASK40_V30_CAMPAIGN_ID,
        "authority": "User-approved Review V30 sections 6.1 and 8 full execution package",
        "active_review_sha": TASK40_V30_REVIEW_COMMIT,
        "active_review_path": TASK40_V30_REVIEW_PATH,
        "active_review_sha256": TASK40_V30_REVIEW_SHA256,
        "source_at_entry": TASK40_V30_SOURCE_AT_ENTRY,
        "review_at_registration": TASK40_V30_REVIEW_COMMIT,
        "t0_utc": "2026-10-12T12:23:42.000Z",
        "numeric_cutoff_utc": "2026-10-13T00:03:42.000Z",
        "deadline_utc": "2026-10-13T00:23:42.000Z",
        "campaign_seconds": TASK40_V30_CAMPAIGN_SECONDS,
        "numeric_cutoff_seconds": 42_000.0,
        "closeout_reserve_seconds": TASK40_V30_CLOSEOUT_RESERVE_SECONDS,
        "time_policy": CONSERVATIVE_REALTIME,
        "stage_scope": list(TASK40_V30_STAGE_SCOPE),
        "forbidden_scope": list(TASK40_V30_FORBIDDEN_SCOPE),
        "window_refreshed": False,
        "old_costs_and_unknowns_preserved": True,
        "artifact_execution_identity_separate": True,
        "bootstrap_boottime_elapsed_seconds": None,
    }
    changed.extend(key for key, value in expected_fields.items() if payload.get(key) != value)
    entry_receipt_path = (repo_root / TASK40_V30_ENTRY_RECEIPT).resolve()
    if (
        not entry_receipt_path.is_file()
        or hashlib.sha256(entry_receipt_path.read_bytes()).hexdigest()
        != TASK40_V30_ENTRY_RECEIPT_SHA256
    ):
        changed.append("controller_entry_receipt_identity")
        controller_entry: Mapping[str, Any] = {}
    else:
        controller_entry = json.loads(entry_receipt_path.read_text(encoding="utf-8"))
    approval = payload.get("user_approval")
    registered_approval = controller_entry.get("user_approval")
    if not isinstance(approval, Mapping) or not isinstance(registered_approval, Mapping) or dict(approval) != dict(registered_approval):
        changed.append("user_approval_does_not_match_original_receipt")
    elif (
        approval.get("scope") != "V30_ALL_Q_REFERENCE_WITH_CONDITIONAL_TARGET_PILOT"
        or approval.get("execution_host") != "fenics-ws"
        or approval.get("execution_root") != "/home/fenics/Projects/laptop_share"
        or approval.get("resources") != {
            "task_memory_max_bytes": 1_649_267_441_664,
            "host_reserve_bytes": 68_719_476_736,
            "memory_swap_max_bytes": 0,
            "mpi_ranks": 1,
            "math_threads": 1,
        }
    ):
        changed.append("user_approval_scope_or_resources")
    else:
        approval_sha = hashlib.sha256(
            json.dumps(approval, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        if payload.get("user_approval_sha256") != approval_sha:
            changed.append("user_approval_sha256")
    parent_window = {
        "path": "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_wsl/campaign_window_v29.json",
        "sha256": "68b19c507106a7ad003a6c7121cb3ba4461ed569bd4706e221970d59126bbf1e",
        "t0_utc": "2026-10-12T05:49:12.144309894Z",
        "deadline_utc": "2026-10-12T11:49:12.144309894Z",
        "verified_expired": True,
        "old_ledger_and_costs_preserved": True,
    }
    if payload.get("parent_window") != parent_window:
        changed.append("prior_v29_window_binding")
    if is_target_window:
        target_receipt_path = (repo_root / TASK40_V30_TARGET_CLOCK_RECEIPT).resolve()
        if (
            not target_receipt_path.is_file()
            or hashlib.sha256(target_receipt_path.read_bytes()).hexdigest()
            != TASK40_V30_TARGET_CLOCK_RECEIPT_SHA256
        ):
            changed.append("target_native_clock_receipt_identity")
            target_receipt: Mapping[str, Any] = {}
        else:
            target_receipt = json.loads(target_receipt_path.read_text(encoding="utf-8"))
        target_identity = target_receipt.get("target", {})
        if (
            target_identity.get("host_alias") != "fenics-ws"
            or target_identity.get("hostname") != "fenics-ws01"
            or target_identity.get("root") != "/home/fenics/Projects/laptop_share"
            or target_identity.get("source_head") != "9a9a9d31f4aebf1564d5f09177c1d3481d64371f"
            or target_identity.get("runtime_profile") != "native_linux"
            or target_identity.get("abi_receipt_sha256") != "1c4277c83a0ac6daf02197086264b9e5b337caee1b33d7cc1dd22a7dfcefe57d"
        ):
            changed.append("target_execution_identity")
        expected_receipt_path = str(TASK40_V30_TARGET_CLOCK_RECEIPT.as_posix())
        if payload.get("target_clock_receipt_path") != expected_receipt_path or payload.get("target_clock_receipt_sha256") != TASK40_V30_TARGET_CLOCK_RECEIPT_SHA256:
            changed.append("target_clock_receipt_binding")
        control_binding = {
            "path": TASK40_V30_CAMPAIGN_WINDOW.as_posix(),
            "sha256": TASK40_V30_CAMPAIGN_SHA256,
            "host_boot_id": str(controller_entry.get("clock_sample", {}).get("boot_id", "")),
            "scope": "local preparation only; not the target-native service window",
        }
        if payload.get("control_window") != control_binding:
            changed.append("separate_control_window_binding")
        raw_anchor = target_receipt.get("first_full_three_clock_sample", {})
    else:
        raw_sample = controller_entry.get("clock_sample", {})
        raw_anchor = {
            "utc_ns": int(raw_sample.get("utc_ns", -1)),
            "monotonic": int(raw_sample.get("monotonic_ns", -1)) / 1e9,
            "boottime": int(raw_sample.get("boottime_ns", -1)) / 1e9,
            "boot_id": str(raw_sample.get("boot_id", "")),
        }
    if payload.get("first_full_three_clock_sample") != raw_anchor:
        changed.append("entry_clock_anchor")
    treatment = payload.get("bootstrap_time_treatment")
    if (
        not isinstance(treatment, str)
        or "UTC elapsed" not in treatment
        or "UNKNOWN" not in treatment
        or "null is not zero" not in treatment
        or "Never refresh T0" not in treatment
        or (is_target_window and "target-native" not in treatment)
        or (not is_target_window and "first preparation" not in treatment)
    ):
        changed.append("bootstrap_time_treatment")
    if changed:
        raise ValueError(f"registered V30 campaign identity or approval changed: {changed}")


@dataclass(frozen=True)
class FixedCampaignWindow:
    path: Path
    sha256: str
    payload: Mapping[str, Any]
    anchor: Mapping[str, Any]
    t0_utc_ns: int
    deadline_utc_ns: int
    total_seconds: float
    bootstrap_seconds: float
    closeout_seconds: float

    @property
    def accounting_path(self) -> Path:
        configured = self.payload.get("accounting_path")
        return Path(str(configured)).resolve() if configured else self.path.parent / CAMPAIGN_ACCOUNTING_NAME

    @property
    def cutoff_seconds(self) -> float:
        return self.total_seconds - self.closeout_seconds

    def remaining_seconds(
        self,
        *,
        phase: str,
        cumulative_charged_seconds: float,
        now_utc_ns: int,
        sub_budget_seconds: float | None = None,
        termination_reserve_seconds: float = 0.0,
    ) -> float:
        """Return the conservative remaining budget for one registered phase."""
        if phase not in {"numeric", "closeout"}:
            raise ValueError("campaign phase must be numeric or closeout")
        values = (float(cumulative_charged_seconds),)
        if any(not math.isfinite(value) or value < 0.0 for value in values):
            raise ValueError("campaign charged time must be finite and nonnegative")
        if type(now_utc_ns) is not int or now_utc_ns < 0:
            raise ValueError("campaign UTC sample must be a nonnegative integer")
        if sub_budget_seconds is not None and (
            not math.isfinite(float(sub_budget_seconds))
            or float(sub_budget_seconds) <= 0.0
        ):
            raise ValueError("campaign phase sub-budget must be finite and positive")
        if (
            not math.isfinite(float(termination_reserve_seconds))
            or float(termination_reserve_seconds) < 0.0
            or (phase == "numeric" and float(termination_reserve_seconds) != 0.0)
        ):
            raise ValueError("termination reserve is allowed only as a nonnegative closeout budget")
        total_remaining = self.total_seconds - float(cumulative_charged_seconds)
        utc_remaining = (self.deadline_utc_ns - int(now_utc_ns)) / 1e9
        if phase == "numeric":
            phase_remaining = min(
                self.cutoff_seconds - float(cumulative_charged_seconds),
                utc_remaining - self.closeout_seconds,
            )
        else:
            phase_remaining = min(total_remaining, utc_remaining, self.closeout_seconds)
        if sub_budget_seconds is not None:
            phase_remaining = min(phase_remaining, float(sub_budget_seconds))
        if phase == "closeout":
            phase_remaining -= float(termination_reserve_seconds)
        return max(0.0, float(phase_remaining))

    def phase_expired(
        self,
        *,
        phase: str,
        cumulative_charged_seconds: float,
        now_utc_ns: int,
        termination_reserve_seconds: float = 0.0,
    ) -> bool:
        """Use the same charged-time and UTC boundaries at sampling as at launch."""
        return self.remaining_seconds(
            phase=phase,
            cumulative_charged_seconds=cumulative_charged_seconds,
            now_utc_ns=now_utc_ns,
            termination_reserve_seconds=termination_reserve_seconds,
        ) <= 0.0

    def observe(
        self,
        *,
        label: str = "campaign_observation",
        phase: str = "numeric",
        sub_budget_seconds: float | None = None,
        termination_reserve_seconds: float = 0.0,
    ) -> dict[str, Any]:
        record = CampaignAccount(self).record_sample(label=label, phase=phase)
        now = record["sample"]
        remaining = self.remaining_seconds(
            phase=phase,
            cumulative_charged_seconds=float(record["cumulative_charged_seconds"]),
            now_utc_ns=int(now["utc_ns"]),
            sub_budget_seconds=sub_budget_seconds,
            termination_reserve_seconds=termination_reserve_seconds,
        )
        adjacent = float(record["adjacent_interval"]["budget_seconds"])
        cumulative = float(record["cumulative_charged_seconds"])
        return {
            "path": str(self.path),
            "sha256": self.sha256,
            "schema": str(self.payload.get("schema", CAMPAIGN_SCHEMA)),
            "t0_utc_ns": self.t0_utc_ns,
            "deadline_utc_ns": self.deadline_utc_ns,
            "campaign_seconds": self.total_seconds,
            "closeout_reserve_seconds": self.closeout_seconds,
            "phase": phase,
            "bootstrap_charged_seconds": self.bootstrap_seconds,
            "adjacent_charged_seconds": adjacent,
            "cumulative_charged_seconds": cumulative,
            "charged_seconds": cumulative,
            "remaining_numerical_seconds": remaining if phase == "numeric" else 0.0,
            "remaining_closeout_seconds": remaining if phase == "closeout" else 0.0,
            "remaining_phase_seconds": remaining,
            "accounting_record": record,
            "sample": now,
        }


def time_namespace_identity() -> dict[str, str]:
    """Read both Linux time-namespace identities used by the live process."""
    return {
        "time": os.readlink("/proc/self/ns/time"),
        "time_for_children": os.readlink("/proc/self/ns/time_for_children"),
    }


def _last_jsonl_record(stream) -> dict[str, Any] | None:
    stream.seek(0, os.SEEK_END)
    end = stream.tell()
    if end == 0:
        return None
    cursor = end - 1
    stream.seek(cursor)
    if stream.read(1) == b"\n":
        cursor -= 1
    line_start = 0
    while cursor >= 0:
        start = max(0, cursor - 4095)
        stream.seek(start)
        block = stream.read(cursor - start + 1)
        separator = block.rfind(b"\n")
        if separator >= 0:
            line_start = start + separator + 1
            break
        cursor = start - 1
    stream.seek(line_start)
    try:
        value = json.loads(stream.readline())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TimebaseInconsistency("campaign accounting tail is not valid JSON") from exc
    if not isinstance(value, dict):
        raise TimebaseInconsistency("campaign accounting tail is not an object")
    return value


def _close_float(left: Any, right: Any) -> bool:
    try:
        a = float(left)
        b = float(right)
    except (TypeError, ValueError):
        return False
    return math.isfinite(a) and math.isfinite(b) and math.isclose(
        a, b, rel_tol=1.0e-12, abs_tol=1.0e-9
    )


def verify_campaign_accounting_chain(
    window: FixedCampaignWindow,
    path: str | Path | None = None,
) -> dict[str, Any]:
    """Validate and hash one complete append-only ledger before extension."""
    ledger_path = Path(path or window.accounting_path).resolve(strict=True)
    digest = hashlib.sha256()
    previous_sample = dict(window.anchor)
    cumulative = float(window.bootstrap_seconds)
    namespace: dict[str, str] | None = None
    last_record: dict[str, Any] | None = None
    record_count = 0
    with ledger_path.open("rb") as stream:
        for raw_line in stream:
            digest.update(raw_line)
            if not raw_line.endswith(b"\n"):
                raise TimebaseInconsistency("campaign accounting ledger has an incomplete final line")
            try:
                record = json.loads(raw_line)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise TimebaseInconsistency("campaign accounting ledger contains invalid JSON") from error
            if not isinstance(record, dict) or record.get("record_kind") is not None:
                raise TimebaseInconsistency("parent campaign ledger contains a nonstandard record")
            sample = record.get("sample")
            current_namespace = record.get("time_namespace_identity")
            if (
                record.get("schema") != "task40extra.review_v10_campaign_accounting.v1"
                or record.get("sequence") != record_count
                or record.get("campaign_window_sha256") != window.sha256
                or record.get("t0_utc_ns") != window.t0_utc_ns
                or record.get("deadline_utc_ns") != window.deadline_utc_ns
                or record.get("boot_id") != window.anchor.get("boot_id")
                or record.get("bootstrap_charged_seconds") != window.bootstrap_seconds
                or record.get("cutoff_seconds") != window.cutoff_seconds
                or record.get("previous_sample") != previous_sample
                or not isinstance(sample, dict)
                or sample.get("boot_id") != window.anchor.get("boot_id")
                or not isinstance(current_namespace, dict)
                or set(current_namespace) != {"time", "time_for_children"}
                or any(not isinstance(value, str) or not value for value in current_namespace.values())
                or record.get("phase") not in {"numeric", "closeout"}
            ):
                raise TimebaseInconsistency("campaign accounting ledger identity or adjacent-sample chain is broken")
            if namespace is None:
                namespace = dict(current_namespace)
            elif current_namespace != namespace:
                raise TimebaseInconsistency("campaign accounting ledger time namespace changed")
            interval = checked_interval(
                previous_sample, sample, policy=CONSERVATIVE_REALTIME
            )
            recorded_interval = record.get("adjacent_interval")
            if (
                not isinstance(recorded_interval, dict)
                or recorded_interval.get("policy") != interval["policy"]
                or recorded_interval.get("policy_version") != interval["policy_version"]
                or any(
                    not _close_float(recorded_interval.get(key), interval.get(key))
                    for key in (
                        "budget_seconds", "discrepancy_seconds", "tolerance_seconds",
                        "utc_minus_monotonic_seconds",
                    )
                )
                or not isinstance(recorded_interval.get("elapsed_seconds"), dict)
                or any(
                    not _close_float(
                        recorded_interval["elapsed_seconds"].get(key),
                        interval["elapsed_seconds"].get(key),
                    )
                    for key in ("monotonic", "boottime", "utc")
                )
            ):
                raise TimebaseInconsistency("campaign accounting ledger interval was edited or miscomputed")
            cumulative += float(interval["budget_seconds"])
            if not _close_float(record.get("cumulative_charged_seconds"), cumulative):
                raise TimebaseInconsistency("campaign accounting ledger cumulative charge is broken")
            previous_sample = sample
            last_record = record
            record_count += 1
    if record_count == 0 or last_record is None or namespace is None:
        raise TimebaseInconsistency("parent campaign accounting ledger is empty")
    return {
        "path": str(ledger_path),
        "sha256": digest.hexdigest(),
        "bytes": ledger_path.stat().st_size,
        "record_count": record_count,
        "last_sequence": int(last_record["sequence"]),
        "cumulative_charged_seconds": float(cumulative),
        "last_sample": dict(previous_sample),
        "time_namespace_identity": namespace,
        "read_only_verified": True,
    }


def _validate_extension_accounting_seed(
    window: FixedCampaignWindow,
    path: Path,
) -> dict[str, Any] | None:
    extension = window.payload.get("extension")
    if extension is None:
        return None
    if not isinstance(extension, Mapping):
        raise TimebaseInconsistency("campaign extension parent binding is malformed")
    try:
        with path.open("rb") as stream:
            first_line = stream.readline()
        seed = json.loads(first_line)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise TimebaseInconsistency("campaign extension ledger is missing its inherited seed") from error
    if not isinstance(seed, dict):
        raise TimebaseInconsistency("campaign extension ledger seed is not an object")
    if (
        seed.get("record_kind") != "extension_seed"
        or seed.get("schema") != "task40extra.review_v10_campaign_accounting.v1"
        or seed.get("campaign_window_sha256") != window.sha256
        or seed.get("t0_utc_ns") != window.t0_utc_ns
        or seed.get("deadline_utc_ns") != window.deadline_utc_ns
        or seed.get("sequence") != extension.get("parent_last_sequence")
        or seed.get("sample") != extension.get("parent_last_sample")
        or seed.get("previous_sample") != extension.get("parent_last_sample")
        or seed.get("time_namespace_identity") != extension.get("parent_time_namespace_identity")
        or not _close_float(
            seed.get("cumulative_charged_seconds"),
            extension.get("parent_cumulative_charged_seconds"),
        )
        or seed.get("extension_parent") != dict(extension)
        or seed.get("boot_id") != window.anchor.get("boot_id")
        or seed.get("bootstrap_charged_seconds") != window.bootstrap_seconds
        or seed.get("cutoff_seconds") != window.cutoff_seconds
    ):
        raise TimebaseInconsistency("campaign extension ledger seed does not inherit its verified parent charge")
    return seed


def write_campaign_extension_seed(
    window: FixedCampaignWindow,
    parent_state: Mapping[str, Any],
    path: str | Path | None = None,
) -> dict[str, Any]:
    """Create the child ledger's noncharging seed from a verified parent tail."""
    extension = window.payload.get("extension")
    if not isinstance(extension, Mapping):
        raise ValueError("fixed campaign window is not an extension")
    expected = {
        "parent_last_sequence": parent_state.get("last_sequence"),
        "parent_cumulative_charged_seconds": parent_state.get("cumulative_charged_seconds"),
        "parent_last_sample": parent_state.get("last_sample"),
        "parent_time_namespace_identity": parent_state.get("time_namespace_identity"),
        "parent_accounting_sha256": parent_state.get("sha256"),
    }
    if any(extension.get(key) != value for key, value in expected.items()):
        raise ValueError("campaign extension window differs from the verified parent ledger tail")
    accounting_path = Path(path or window.accounting_path).resolve()
    accounting_path.parent.mkdir(parents=True, exist_ok=True)
    seed = {
        "schema": "task40extra.review_v10_campaign_accounting.v1",
        "record_kind": "extension_seed",
        "sequence": int(parent_state["last_sequence"]),
        "label": "extension_parent_ledger_inheritance",
        "phase": "numeric",
        "campaign_window_sha256": window.sha256,
        "t0_utc_ns": window.t0_utc_ns,
        "deadline_utc_ns": window.deadline_utc_ns,
        "boot_id": window.anchor["boot_id"],
        "time_namespace_identity": dict(parent_state["time_namespace_identity"]),
        "previous_sample": dict(parent_state["last_sample"]),
        "sample": dict(parent_state["last_sample"]),
        "adjacent_interval": {
            "policy": "parent_ledger_inheritance",
            "budget_seconds": 0.0,
            "scope": "seed carries prior cumulative charge and adds no interval",
        },
        "bootstrap_charged_seconds": window.bootstrap_seconds,
        "cumulative_charged_seconds": float(parent_state["cumulative_charged_seconds"]),
        "cutoff_seconds": window.cutoff_seconds,
        "extension_parent": dict(extension),
    }
    if accounting_path.exists():
        existing = _validate_extension_accounting_seed(window, accounting_path)
        if existing != seed:
            raise FileExistsError("existing campaign extension ledger seed differs; preserving it")
    else:
        with accounting_path.open("xb") as stream:
            stream.write(
                (json.dumps(seed, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
            )
            stream.flush()
            os.fsync(stream.fileno())
        descriptor = os.open(accounting_path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    _validate_extension_accounting_seed(window, accounting_path)
    return {
        "path": str(accounting_path),
        "seed": seed,
        "sha256": hashlib.sha256(accounting_path.read_bytes()).hexdigest(),
        "bytes": accounting_path.stat().st_size,
    }


class CampaignAccount:
    """Append-only adjacent clock accounting shared across service attempts."""

    def __init__(self, window: FixedCampaignWindow, path: str | Path | None = None):
        self.window = window
        self.path = Path(path or window.accounting_path).resolve()

    def record_sample(
        self,
        sample: Mapping[str, Any] | None = None,
        *,
        label: str,
        phase: str = "numeric",
        namespace_identity: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        if phase not in {"numeric", "closeout"}:
            raise ValueError("campaign accounting phase must be numeric or closeout")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _validate_extension_accounting_seed(self.window, self.path)
        with self.path.open("a+b") as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            # Capture clocks and namespace only after the exclusive lock. This
            # keeps the single-writer sequence aligned with the sample order.
            current = dict(sample or clock_sample(include_boot_id=True))
            namespace = dict(namespace_identity or time_namespace_identity())
            if current.get("boot_id") != self.window.anchor.get("boot_id"):
                raise TimebaseInconsistency(
                    "campaign sample boot identity differs from the fixed window"
                )
            if set(namespace) != {"time", "time_for_children"} or any(
                not isinstance(value, str) or not value for value in namespace.values()
            ):
                raise TimebaseInconsistency(
                    "campaign time-namespace identity is incomplete"
                )
            previous = _last_jsonl_record(stream)
            if previous is None:
                previous_sample = dict(self.window.anchor)
                cumulative = self.window.bootstrap_seconds
                prior_namespace = namespace
                sequence = 0
            else:
                if (
                    previous.get("schema")
                    != "task40extra.review_v10_campaign_accounting.v1"
                    or previous.get("campaign_window_sha256") != self.window.sha256
                    or previous.get("boot_id") != self.window.anchor.get("boot_id")
                ):
                    raise TimebaseInconsistency(
                        "campaign accounting is bound to a different window or boot"
                    )
                previous_sample = previous.get("sample")
                cumulative = float(previous.get("cumulative_charged_seconds", -1.0))
                prior_namespace = previous.get("time_namespace_identity")
                sequence = int(previous.get("sequence", -1)) + 1
                if (
                    not isinstance(previous_sample, dict)
                    or cumulative < self.window.bootstrap_seconds
                    or prior_namespace != namespace
                ):
                    raise TimebaseInconsistency(
                        "campaign accounting clock or namespace chain is broken"
                    )
            interval = checked_interval(
                previous_sample, current, policy=CONSERVATIVE_REALTIME
            )
            cumulative += float(interval["budget_seconds"])
            record = {
                "schema": "task40extra.review_v10_campaign_accounting.v1",
                "sequence": sequence,
                "label": str(label),
                "phase": phase,
                "campaign_window_sha256": self.window.sha256,
                "t0_utc_ns": self.window.t0_utc_ns,
                "deadline_utc_ns": self.window.deadline_utc_ns,
                "boot_id": self.window.anchor["boot_id"],
                "time_namespace_identity": namespace,
                "previous_sample": previous_sample,
                "sample": current,
                "adjacent_interval": interval,
                "bootstrap_charged_seconds": self.window.bootstrap_seconds,
                "cumulative_charged_seconds": cumulative,
                "cutoff_seconds": self.window.cutoff_seconds,
            }
            stream.seek(0, os.SEEK_END)
            stream.write(
                (
                    json.dumps(
                        record, sort_keys=True, separators=(",", ":"), allow_nan=False
                    )
                    + "\n"
                ).encode()
            )
            stream.flush()
            os.fsync(stream.fileno())
            return record


def read_campaign_state(
    window: FixedCampaignWindow,
    path: str | Path | None = None,
    *,
    sample: Mapping[str, Any] | None = None,
    phase: str = "numeric",
    sub_budget_seconds: float | None = None,
    termination_reserve_seconds: float = 0.0,
    namespace_identity: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Read worker-visible remaining time without appending to the shared ledger."""
    account_path = Path(path or window.accounting_path).resolve()
    _validate_extension_accounting_seed(window, account_path)
    with account_path.open("rb") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_SH)
        previous = _last_jsonl_record(stream)
        current = dict(sample or clock_sample(include_boot_id=True))
        namespace = dict(namespace_identity or time_namespace_identity())
        if previous is None:
            raise TimebaseInconsistency("campaign worker started before the watchdog bound its clock")
        if (
            previous.get("schema") != "task40extra.review_v10_campaign_accounting.v1"
            or previous.get("campaign_window_sha256") != window.sha256
            or previous.get("boot_id") != window.anchor.get("boot_id")
            or previous.get("deadline_utc_ns") != window.deadline_utc_ns
        ):
            raise TimebaseInconsistency("campaign worker read a different fixed window or boot")
        if current.get("boot_id") != window.anchor.get("boot_id"):
            raise TimebaseInconsistency("campaign worker boot identity differs from the fixed window")
        if previous.get("time_namespace_identity") != namespace:
            raise TimebaseInconsistency("campaign worker time namespace differs from the watchdog")
        last_sample = previous.get("sample")
        cumulative = float(previous.get("cumulative_charged_seconds", -1.0))
        if not isinstance(last_sample, dict) or cumulative < window.bootstrap_seconds:
            raise TimebaseInconsistency("campaign worker read an incomplete accounting tail")
        adjacent = checked_interval(
            last_sample, current, policy=CONSERVATIVE_REALTIME
        )
        projected_cumulative = cumulative + float(adjacent["budget_seconds"])
        remaining = window.remaining_seconds(
            phase=phase,
            cumulative_charged_seconds=projected_cumulative,
            now_utc_ns=int(current["utc_ns"]),
            sub_budget_seconds=sub_budget_seconds,
            termination_reserve_seconds=termination_reserve_seconds,
        )
        return {
            "path": str(account_path),
            "campaign_window_sha256": window.sha256,
            "t0_utc_ns": window.t0_utc_ns,
            "deadline_utc_ns": window.deadline_utc_ns,
            "phase": phase,
            "accounting_record": previous,
            "sample": current,
            "adjacent_interval": adjacent,
            "projected_cumulative_charged_seconds": projected_cumulative,
            "remaining_numerical_seconds": remaining if phase == "numeric" else 0.0,
            "remaining_closeout_seconds": remaining if phase == "closeout" else 0.0,
            "remaining_phase_seconds": remaining,
            "read_only": True,
        }


def _validate_v31_campaign_registration(
    resolved: Path,
    digest: str,
    payload: Mapping[str, Any],
    contract: Mapping[str, Any],
    *,
    review_version: str = "V31",
) -> None:
    from src.runners.task40_v31_contract import (
        V31_APPROVAL_SCOPE, V31_NUMERIC_SECONDS, V31_REVIEW_COMMIT, V31_REVIEW_PATH,
        V31_REVIEW_SHA256, V31_STAGE_SCOPE, V32_APPROVAL_SCOPE, V32_NUMERIC_SECONDS,
        V32_REVIEW_COMMIT, V32_REVIEW_PATH, V32_REVIEW_SHA256, V32_STAGE_SCOPE,
        V33_APPROVAL_SCOPE, V33_NUMERIC_SECONDS, V33_REVIEW_COMMIT, V33_REVIEW_PATH,
        V33_REVIEW_SHA256, V33_STAGE_SCOPE, V33_TOTAL_SECONDS, V33_CLOSEOUT_SECONDS,
        V33_EXTENSION_APPROVAL_SCOPE, V33_EXTENSION_NUMERIC_SECONDS,
        V33_EXTENSION_TOTAL_SECONDS, V33_EXTENSION_CLOSEOUT_SECONDS,
    )

    authority = f"User-approved Review {review_version} execution window"
    if review_version == "V31":
        review_commit, review_path, review_sha = V31_REVIEW_COMMIT, V31_REVIEW_PATH, V31_REVIEW_SHA256
        campaign = "task40extra_v31_all_q_reference_conditional_target_pilot"
        total_seconds = TASK40_V31_CAMPAIGN_SECONDS
        numeric_seconds = V31_NUMERIC_SECONDS
        closeout_seconds = TASK40_V31_CLOSEOUT_RESERVE_SECONDS
        stage_scope, approval_scope = V31_STAGE_SCOPE, V31_APPROVAL_SCOPE
    elif review_version == "V32":
        review_commit, review_path, review_sha = V32_REVIEW_COMMIT, V32_REVIEW_PATH, V32_REVIEW_SHA256
        campaign = "task40extra_v32_all_q_reference_conditional_target_pilot"
        total_seconds = TASK40_V32_CAMPAIGN_SECONDS
        numeric_seconds = V32_NUMERIC_SECONDS
        closeout_seconds = TASK40_V32_CLOSEOUT_RESERVE_SECONDS
        stage_scope, approval_scope = V32_STAGE_SCOPE, V32_APPROVAL_SCOPE
    elif review_version == "V33":
        review_commit, review_path, review_sha = V33_REVIEW_COMMIT, V33_REVIEW_PATH, V33_REVIEW_SHA256
        campaign = "task40extra_v33_all_q_reference_conditional_target_pilot"
        total_seconds = V33_TOTAL_SECONDS
        numeric_seconds = V33_NUMERIC_SECONDS
        closeout_seconds = V33_CLOSEOUT_SECONDS
        stage_scope, approval_scope = V33_STAGE_SCOPE, V33_APPROVAL_SCOPE
    elif review_version == "V33_EXTENSION":
        review_commit, review_path, review_sha = V33_REVIEW_COMMIT, V33_REVIEW_PATH, V33_REVIEW_SHA256
        campaign = "task40extra_v33_extension_all_q_reference_conditional_target_pilot"
        total_seconds = V33_EXTENSION_TOTAL_SECONDS
        numeric_seconds = V33_EXTENSION_NUMERIC_SECONDS
        closeout_seconds = V33_EXTENSION_CLOSEOUT_SECONDS
        stage_scope, approval_scope = V33_STAGE_SCOPE, V33_EXTENSION_APPROVAL_SCOPE
        authority = "User-authorized 86400-second extension of the original Review V33 window"
    else:
        raise ValueError("review version must be V31, V32, or V33")

    execution = contract.get("execution")
    window = execution.get("window") if isinstance(execution, Mapping) else None
    source = contract.get("source_freeze")
    expected_path = Path(str(window.get("window_path", ""))).resolve() if isinstance(window, Mapping) else None
    expected_sha = window.get("window_sha256") if isinstance(window, Mapping) else None
    entry_source = window.get("source_at_entry") if isinstance(window, Mapping) else None
    run_source = execution.get("run_source_sha") if isinstance(execution, Mapping) else None
    if not isinstance(entry_source, str) or not re.fullmatch(r"[0-9a-f]{40}", entry_source):
        raise ValueError("V31 fixed window must preserve its original 40-character source_at_entry")
    if (
        not isinstance(source, Mapping)
        or source.get("source_sha") != run_source
        or not isinstance(run_source, str)
        or not re.fullmatch(r"[0-9a-f]{40}", run_source)
    ):
        raise ValueError("V31 run_source_sha must bind this run's clean source freeze")
    expected_fields = {
        "schema": CAMPAIGN_SCHEMA,
        "campaign": campaign,
        "authority": authority,
        "active_review_sha": review_commit,
        "active_review_path": review_path,
        "active_review_sha256": review_sha,
        "source_at_entry": entry_source,
        "review_at_registration": review_commit,
        "t0_utc": window.get("t0_utc") if isinstance(window, Mapping) else None,
        "numeric_cutoff_utc": window.get("numeric_cutoff_utc") if isinstance(window, Mapping) else None,
        "deadline_utc": window.get("deadline_utc") if isinstance(window, Mapping) else None,
        "campaign_seconds": total_seconds,
        "numeric_cutoff_seconds": float(numeric_seconds),
        "closeout_reserve_seconds": closeout_seconds,
        "time_policy": CONSERVATIVE_REALTIME,
        "stage_scope": list(stage_scope),
        "forbidden_scope": [
            "automatic_cap_increase", "window_refresh", "parameter_or_accuracy_scan",
            "MUMPS_or_ABI_change", "OOC_or_BLR", "unrelated_project_mutation", "master_merge",
        ],
        "window_refreshed": False,
        "old_costs_and_unknowns_preserved": True,
        "artifact_execution_identity_separate": True,
        "bootstrap_boottime_elapsed_seconds": None,
    }
    changed = [key for key, value in expected_fields.items() if payload.get(key) != value]
    if review_version == "V33_EXTENSION":
        extension = payload.get("extension")
        contract_extension = contract.get("extension_authorization")
        if (
            not isinstance(extension, Mapping)
            or not isinstance(contract_extension, Mapping)
            or extension.get("schema") != "task40extra.review_v33_window_extension.v1"
            or extension.get("extension_seconds") != 86_400
            or extension.get("original_t0_utc") != payload.get("t0_utc")
            or extension.get("parent_window_sha256") != contract_extension.get("parent_window_sha256")
            or extension.get("parent_accounting_sha256") != contract_extension.get("parent_accounting_sha256")
            or extension.get("authorization_record_sha256") != contract_extension.get("authorization_record_sha256")
            or extension.get("parent_cumulative_charged_seconds") is None
            or extension.get("parent_last_sequence") is None
            or contract_extension.get("extension_seconds") != 86_400
            or contract_extension.get("window_sha256") != digest
            or not isinstance(payload.get("accounting_path"), str)
            or Path(str(payload.get("accounting_path"))).resolve()
            != Path(str(contract_extension.get("accounting_path", ""))).resolve()
            or Path(str(payload.get("accounting_path"))).resolve()
            != (resolved.parent / "campaign_accounting_v33_extension.jsonl").resolve()
        ):
            changed.append("extension_parent_or_accounting_binding")
    if resolved != expected_path or digest != expected_sha:
        changed.extend(("campaign_window_path", "campaign_window_sha256"))
    approval = contract.get("user_approval")
    if (
        contract.get("status") != "USER_APPROVED"
        or not isinstance(approval, Mapping)
        or approval.get("approved") is not True
        or approval.get("scope") != approval_scope
        or approval.get("window_sha256") != digest
    ):
        changed.append("user_approval")
    if changed:
        raise ValueError(
            f"registered {review_version} campaign identity or scope changed: {sorted(set(changed))}"
        )


def load_fixed_campaign_window(
    path: str | Path = TASK40_V10_CAMPAIGN_WINDOW,
    *,
    require_current_boot: bool = True,
    v31_contract: Mapping[str, Any] | None = None,
) -> FixedCampaignWindow:
    resolved = Path(path).resolve()
    raw = resolved.read_bytes()
    payload = json.loads(raw)
    if not isinstance(payload, dict) or payload.get("schema") != CAMPAIGN_SCHEMA:
        raise ValueError("the fixed Task40 V10 campaign window schema is invalid")
    if payload.get("window_refreshed") is not False or payload.get(
        "old_costs_and_unknowns_preserved"
    ) is not True:
        raise ValueError("the fixed campaign window was refreshed or erased prior costs")
    digest = hashlib.sha256(raw).hexdigest()
    v22_path = (
        Path(__file__).resolve().parents[2] / TASK40_V22_CAMPAIGN_WINDOW
    ).resolve()
    v23_path = (
        Path(__file__).resolve().parents[2] / TASK40_V23_CAMPAIGN_WINDOW
    ).resolve()
    v24_path = (
        Path(__file__).resolve().parents[2] / TASK40_V24_CAMPAIGN_WINDOW
    ).resolve()
    v25_path = (
        Path(__file__).resolve().parents[2] / TASK40_V25_CAMPAIGN_WINDOW
    ).resolve()
    v26_path = (
        Path(__file__).resolve().parents[2] / TASK40_V26_CAMPAIGN_WINDOW
    ).resolve()
    v27_path = (
        Path(__file__).resolve().parents[2] / TASK40_V27_CAMPAIGN_WINDOW
    ).resolve()
    v28_path = (
        Path(__file__).resolve().parents[2] / TASK40_V28_CAMPAIGN_WINDOW
    ).resolve()
    v29_path = (
        Path(__file__).resolve().parents[2] / TASK40_V29_CAMPAIGN_WINDOW
    ).resolve()
    v30_path = (
        Path(__file__).resolve().parents[2] / TASK40_V30_CAMPAIGN_WINDOW
    ).resolve()
    v30_target_path = (
        Path(__file__).resolve().parents[2] / TASK40_V30_TARGET_CAMPAIGN_WINDOW
    ).resolve()
    v31_artifact_root = (
        Path(__file__).resolve().parents[2]
        / Path("benchmarks/artifacts/task40extra_0p7nm_engineering/local_v31_native")
    ).resolve()
    is_v22 = resolved == v22_path
    is_v23 = resolved == v23_path
    is_v24 = resolved == v24_path
    is_v25 = resolved == v25_path
    is_v26 = resolved == v26_path
    is_v27 = resolved == v27_path
    is_v28 = resolved == v28_path
    is_v29 = resolved == v29_path
    is_v30 = resolved in {v30_path, v30_target_path}
    is_v31 = (
        resolved.name == "campaign_window_v31.json"
        and resolved.parent.parent == v31_artifact_root
        and re.fullmatch(r"source_[0-9a-f]{40}", resolved.parent.name) is not None
    )
    is_v32 = (
        resolved.name == "campaign_window_v32.json"
        and resolved.parent.parent == v31_artifact_root
        and re.fullmatch(r"source_[0-9a-f]{40}", resolved.parent.name) is not None
    )
    is_v33_extension = (
        resolved.name == "campaign_window_v33.json"
        and resolved.parent.parent == v31_artifact_root
        and re.fullmatch(r"source_[0-9a-f]{40}", resolved.parent.name) is not None
        and payload.get("campaign")
        == "task40extra_v33_extension_all_q_reference_conditional_target_pilot"
    )
    is_v33 = (
        resolved.name == "campaign_window_v33.json"
        and resolved.parent.parent == v31_artifact_root
        and re.fullmatch(r"source_[0-9a-f]{40}", resolved.parent.name) is not None
        and payload.get("campaign")
        == "task40extra_v33_all_q_reference_conditional_target_pilot"
    )
    if is_v22:
        _validate_v22_campaign_registration(resolved, digest, payload)
        expected_total = TASK40_V22_CAMPAIGN_SECONDS
        expected_closeout = TASK40_V22_CLOSEOUT_RESERVE_SECONDS
    elif is_v23:
        _validate_v23_campaign_registration(resolved, digest, payload)
        expected_total = TASK40_V23_CAMPAIGN_SECONDS
        expected_closeout = TASK40_V23_CLOSEOUT_RESERVE_SECONDS
    elif is_v24:
        _validate_v24_campaign_registration(resolved, digest, payload)
        expected_total = TASK40_V24_CAMPAIGN_SECONDS
        expected_closeout = TASK40_V24_CLOSEOUT_RESERVE_SECONDS
    elif is_v25:
        _validate_v25_campaign_registration(resolved, digest, payload)
        expected_total = TASK40_V25_CAMPAIGN_SECONDS
        expected_closeout = TASK40_V25_CLOSEOUT_RESERVE_SECONDS
    elif is_v26:
        _validate_v26_campaign_registration(resolved, digest, payload)
        expected_total = TASK40_V26_CAMPAIGN_SECONDS
        expected_closeout = TASK40_V26_CLOSEOUT_RESERVE_SECONDS
    elif is_v27:
        _validate_v27_campaign_registration(resolved, digest, payload)
        expected_total = TASK40_V27_CAMPAIGN_SECONDS
        expected_closeout = TASK40_V27_CLOSEOUT_RESERVE_SECONDS
    elif is_v28:
        _validate_v28_campaign_registration(resolved, digest, payload)
        expected_total = TASK40_V28_CAMPAIGN_SECONDS
        expected_closeout = TASK40_V28_CLOSEOUT_RESERVE_SECONDS
    elif is_v29:
        _validate_v29_campaign_registration(resolved, digest, payload)
        expected_total = TASK40_V29_CAMPAIGN_SECONDS
        expected_closeout = TASK40_V29_CLOSEOUT_RESERVE_SECONDS
    elif is_v30:
        _validate_v30_campaign_registration(resolved, digest, payload)
        expected_total = TASK40_V30_CAMPAIGN_SECONDS
        expected_closeout = TASK40_V30_CLOSEOUT_RESERVE_SECONDS
    elif is_v31 or is_v32 or is_v33 or is_v33_extension:
        review_version = "V33_EXTENSION" if is_v33_extension else "V33" if is_v33 else "V32" if is_v32 else "V31"
        if v31_contract is None:
            contract_path = os.environ.get("TASK40_V31_CONTRACT_PATH")
            contract_sha = os.environ.get("TASK40_V31_CONTRACT_SHA256")
            if not contract_path or not contract_sha:
                raise ValueError(f"{review_version} campaign window requires its approved execution contract")
            from src.runners.task40_v31_contract import require_v31_execution_contract

            v31_contract, _ = require_v31_execution_contract(
                contract_path, expected_sha256=contract_sha, current_root=Path.cwd()
            )
        _validate_v31_campaign_registration(
            resolved,
            digest,
            payload,
            v31_contract,
            review_version=review_version,
        )
        if is_v33_extension:
            expected_total = TASK40_V33_EXTENSION_TOTAL_SECONDS
            expected_closeout = TASK40_V33_EXTENSION_CLOSEOUT_SECONDS
        elif is_v33:
            expected_total = TASK40_V33_CAMPAIGN_SECONDS
            expected_closeout = TASK40_V33_CLOSEOUT_RESERVE_SECONDS
        elif is_v32:
            expected_total = TASK40_V32_CAMPAIGN_SECONDS
            expected_closeout = TASK40_V32_CLOSEOUT_RESERVE_SECONDS
        else:
            expected_total = TASK40_V31_CAMPAIGN_SECONDS
            expected_closeout = TASK40_V31_CLOSEOUT_RESERVE_SECONDS
    else:
        expected_total = CAMPAIGN_SECONDS
        expected_closeout = CLOSEOUT_RESERVE_SECONDS
    total = float(payload.get("campaign_seconds", 0.0))
    if total != expected_total or payload.get("time_policy") != CONSERVATIVE_REALTIME:
        raise ValueError("the fixed campaign duration or clock policy differs from its registration")
    t0_ns = _utc_ns(payload.get("t0_utc"))
    deadline_ns = _utc_ns(payload.get("deadline_utc"))
    if deadline_ns - t0_ns != int(total * 1e9):
        raise ValueError("the fixed campaign deadline does not equal its registered T0 plus duration")
    initial = payload.get("first_full_three_clock_sample")
    if not isinstance(initial, dict):
        raise ValueError("the initial full monotone/UTC/boot sample is missing")
    anchor = {
        "monotonic": float(initial["monotonic"]),
        "boottime": float(initial["boottime"]),
        "utc_ns": int(initial["utc_ns"]),
        "boot_id": str(initial["boot_id"]),
    }
    if (
        not re.fullmatch(r"[0-9a-fA-F-]{36}", anchor["boot_id"])
        or payload.get("initial_boot_id") != anchor["boot_id"]
    ):
        raise ValueError("the initial boot identity is malformed or inconsistent")
    bootstrap_utc = float(payload.get("bootstrap_utc_elapsed_seconds", -1.0))
    bootstrap_boot_raw = payload.get("bootstrap_boottime_elapsed_seconds", -1.0)
    if (is_v30 or is_v31 or is_v32 or is_v33 or is_v33_extension) and bootstrap_boot_raw is None:
        bootstrap_boot = None
    else:
        bootstrap_boot = float(bootstrap_boot_raw)
    if bootstrap_utc < 0 or (bootstrap_boot is not None and bootstrap_boot < 0):
        raise ValueError("campaign bootstrap accounting must be non-negative when measured")
    bootstrap = max(bootstrap_utc, bootstrap_boot if bootstrap_boot is not None else bootstrap_utc)
    if abs((anchor["utc_ns"] - t0_ns) / 1e9 - bootstrap_utc) > 1e-6:
        raise ValueError("the recorded UTC bootstrap debit does not match the immutable T0")
    if payload.get("bootstrap_time_treatment") is None:
        raise ValueError("campaign startup and preparation costs are not accounted")
    closeout = float(payload.get("closeout_reserve_seconds", CLOSEOUT_RESERVE_SECONDS))
    if closeout != expected_closeout or closeout >= total:
        raise ValueError("the fixed campaign closeout reserve changed")
    if require_current_boot:
        now = clock_sample(include_boot_id=True)
        if now.get("boot_id") != anchor["boot_id"]:
            raise TimebaseInconsistency("WSL boot identity changed during the active V10 campaign")
    return FixedCampaignWindow(
        path=resolved,
        sha256=digest,
        payload=payload,
        anchor=anchor,
        t0_utc_ns=t0_ns,
        deadline_utc_ns=deadline_ns,
        total_seconds=total,
        bootstrap_seconds=bootstrap,
        closeout_seconds=closeout,
    )


__all__ = [
    "CAMPAIGN_ACCOUNTING_NAME",
    "CAMPAIGN_SCHEMA",
    "CLOSEOUT_RESERVE_SECONDS",
    "TASK40_V22_CAMPAIGN_WINDOW",
    "TASK40_V22_CAMPAIGN_SHA256",
    "TASK40_V22_CAMPAIGN_SECONDS",
    "TASK40_V22_CLOSEOUT_RESERVE_SECONDS",
    "TASK40_V22_CAMPAIGN_ID",
    "TASK40_V22_REVIEW_SHA",
    "TASK40_V22_REVIEW_PATH",
    "TASK40_V22_STAGE_SCOPE",
    "TASK40_V22_FORBIDDEN_SCOPE",
    "TASK40_V22_PARENT_WINDOW",
    "TASK40_V22_PARENT_LEDGER",
    "TASK40_V23_CAMPAIGN_WINDOW",
    "TASK40_V23_CAMPAIGN_SHA256",
    "TASK40_V23_CAMPAIGN_SECONDS",
    "TASK40_V23_CLOSEOUT_RESERVE_SECONDS",
    "TASK40_V23_CAMPAIGN_ID",
    "TASK40_V23_REVIEW_COMMIT",
    "TASK40_V23_REVIEW_SHA256",
    "TASK40_V23_REVIEW_PATH",
    "TASK40_V23_SOURCE_AT_ENTRY",
    "TASK40_V23_STAGE_SCOPE",
    "TASK40_V23_FORBIDDEN_SCOPE",
    "TASK40_V23_PARENT_WINDOW",
    "TASK40_V23_PARENT_LEDGER",
    "TASK40_V24_CAMPAIGN_WINDOW",
    "TASK40_V24_CAMPAIGN_SHA256",
    "TASK40_V24_CAMPAIGN_RECEIPT",
    "TASK40_V24_CAMPAIGN_RECEIPT_SHA256",
    "TASK40_V24_CAMPAIGN_SECONDS",
    "TASK40_V24_CLOSEOUT_RESERVE_SECONDS",
    "TASK40_V24_CAMPAIGN_ID",
    "TASK40_V24_REVIEW_COMMIT",
    "TASK40_V24_REVIEW_SHA256",
    "TASK40_V24_REVIEW_PATH",
    "TASK40_V24_SOURCE_AT_ENTRY",
    "TASK40_V24_STAGE_SCOPE",
    "TASK40_V24_FORBIDDEN_SCOPE",
    "TASK40_V24_PARENT_WINDOW",
    "TASK40_V24_PARENT_LEDGER",
    "TASK40_V25_CAMPAIGN_WINDOW",
    "TASK40_V25_CAMPAIGN_SHA256",
    "TASK40_V25_CAMPAIGN_RECEIPT",
    "TASK40_V25_CAMPAIGN_RECEIPT_SHA256",
    "TASK40_V25_CAMPAIGN_SECONDS",
    "TASK40_V25_CLOSEOUT_RESERVE_SECONDS",
    "TASK40_V25_CAMPAIGN_ID",
    "TASK40_V25_REVIEW_COMMIT",
    "TASK40_V25_REVIEW_SHA256",
    "TASK40_V25_REVIEW_PATH",
    "TASK40_V25_SOURCE_AT_ENTRY",
    "TASK40_V25_STAGE_SCOPE",
    "TASK40_V25_FORBIDDEN_SCOPE",
    "TASK40_V25_PARENT_WINDOW",
    "TASK40_V25_PARENT_LEDGER",
    "TASK40_V26_CAMPAIGN_WINDOW",
    "TASK40_V26_CAMPAIGN_SHA256",
    "TASK40_V26_CAMPAIGN_RECEIPT",
    "TASK40_V26_CAMPAIGN_RECEIPT_SHA256",
    "TASK40_V26_CAMPAIGN_SECONDS",
    "TASK40_V26_CLOSEOUT_RESERVE_SECONDS",
    "TASK40_V26_CAMPAIGN_ID",
    "TASK40_V26_REVIEW_COMMIT",
    "TASK40_V26_REVIEW_SHA256",
    "TASK40_V26_REVIEW_PATH",
    "TASK40_V26_SOURCE_AT_ENTRY",
    "TASK40_V26_STAGE_SCOPE",
    "TASK40_V26_FORBIDDEN_SCOPE",
    "TASK40_V26_PARENT_WINDOW",
    "TASK40_V26_PARENT_LEDGER",
    "TASK40_V27_CAMPAIGN_WINDOW",
    "TASK40_V27_CAMPAIGN_SHA256",
    "TASK40_V27_CAMPAIGN_RECEIPT",
    "TASK40_V27_CAMPAIGN_RECEIPT_SHA256",
    "TASK40_V27_CAMPAIGN_SECONDS",
    "TASK40_V27_CLOSEOUT_RESERVE_SECONDS",
    "TASK40_V27_CAMPAIGN_ID",
    "TASK40_V27_REVIEW_COMMIT",
    "TASK40_V27_REVIEW_SHA256",
    "TASK40_V27_REVIEW_PATH",
    "TASK40_V27_SOURCE_AT_ENTRY",
    "TASK40_V27_STAGE_SCOPE",
    "TASK40_V27_FORBIDDEN_SCOPE",
    "TASK40_V27_PARENT_WINDOW",
    "TASK40_V27_PARENT_LEDGER",
    "TASK40_V28_CAMPAIGN_WINDOW",
    "TASK40_V28_CAMPAIGN_SHA256",
    "TASK40_V28_CAMPAIGN_RECEIPT",
    "TASK40_V28_CAMPAIGN_RECEIPT_SHA256",
    "TASK40_V28_CAMPAIGN_SECONDS",
    "TASK40_V28_CLOSEOUT_RESERVE_SECONDS",
    "TASK40_V28_CAMPAIGN_ID",
    "TASK40_V28_REVIEW_COMMIT",
    "TASK40_V28_REVIEW_SHA256",
    "TASK40_V28_REVIEW_PATH",
    "TASK40_V28_SOURCE_AT_ENTRY",
    "TASK40_V28_STAGE_SCOPE",
    "TASK40_V28_FORBIDDEN_SCOPE",
    "TASK40_V28_PARENT_WINDOW",
    "TASK40_V28_PARENT_LEDGER",
    "TASK40_V29_CAMPAIGN_WINDOW",
    "TASK40_V29_CAMPAIGN_SECONDS",
    "TASK40_V29_CLOSEOUT_RESERVE_SECONDS",
    "TASK40_V29_CAMPAIGN_ID",
    "TASK40_V29_REVIEW_COMMIT",
    "TASK40_V29_REVIEW_SHA256",
    "TASK40_V29_REVIEW_PATH",
    "TASK40_V29_STAGE_SCOPE",
    "TASK40_V29_FORBIDDEN_SCOPE",
    "TASK40_V30_CAMPAIGN_WINDOW",
    "TASK40_V30_CAMPAIGN_SHA256",
    "TASK40_V30_TARGET_CAMPAIGN_WINDOW",
    "TASK40_V30_TARGET_CAMPAIGN_SHA256",
    "TASK40_V30_TARGET_CLOCK_RECEIPT",
    "TASK40_V30_TARGET_CLOCK_RECEIPT_SHA256",
    "TASK40_V30_ENTRY_RECEIPT",
    "TASK40_V30_ENTRY_RECEIPT_SHA256",
    "TASK40_V30_CAMPAIGN_SECONDS",
    "TASK40_V30_CLOSEOUT_RESERVE_SECONDS",
    "TASK40_V30_CAMPAIGN_ID",
    "TASK40_V30_REVIEW_COMMIT",
    "TASK40_V30_REVIEW_SHA256",
    "TASK40_V30_REVIEW_PATH",
    "TASK40_V30_SOURCE_AT_ENTRY",
    "TASK40_V30_STAGE_SCOPE",
    "TASK40_V30_FORBIDDEN_SCOPE",
    "CampaignAccount",
    "FixedCampaignWindow",
    "TASK40_V10_CAMPAIGN_WINDOW",
    "load_fixed_campaign_window",
    "read_campaign_state",
    "time_namespace_identity",
]
