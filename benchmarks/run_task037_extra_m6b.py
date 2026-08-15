"""Thin M6B shifted-screen stage, builder, online, and checker entry point.

The controller remains standard-library only; DOLFINx/PETSc are imported only
inside the three workers.  Numeric patch/action logic lives in ``src`` and the
checker reads raw evidence rather than rebuilding a finite-element operator.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys
from typing import Any, Callable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
M6B_SCHEMA = "task037.extra.h2b.m6b.v1"
M6B_STAGE_SCHEMA = f"{M6B_SCHEMA}.stage"
M6B_BUILDER_SCHEMA = f"{M6B_SCHEMA}.builder"
M6B_WORKER_SCHEMA = f"{M6B_SCHEMA}.worker"
M6B_WATCHDOG_SCHEMA = f"{M6B_SCHEMA}.watchdog"
M6B_CHECK_SCHEMA = f"{M6B_SCHEMA}.check"
M6B_DEGREE = 6
M6B_H_NM = 10.0
M6B_GLOBAL_CELLS = 252
M6B_LOCAL_NLOC = 882
M6B_GLOBAL_ROWS = 173_802
M6B_CONSTRAINTS = 9_210
M6B_BETA = 0.5
M6B_SHARED_VOLUME_OPERATOR = (
    "C-k0^2*M_epsilon+i*beta*k0^2*M_abs_epsilon"
)
M6B_SHIFTED_OPERATOR = (
    "B_beta=Kcurl-k0^2*M_epsilon+i*beta*k0^2*M_abs_epsilon"
)
M6B_SHARED_VOLUME_REPRESENTATION = "exact_DG0_single_integral"
M6B_SHARED_VOLUME_SCHEMA = "task037.extra.h2b.m6b.shared-volume.v1"
M6B_FACTOR_COUNT = 84
M6B_FACTOR_REUSE = 168
M6B_RETAINED_TOTAL_LIMIT_BYTES = 1_100_000_000
M6B_WATCHDOG_RSS_LIMIT_BYTES = 1_950_000_000
M6B_ONLINE_COMPLETION_RSS_LIMIT_BYTES = 1_900_000_000
M6B_STAGE_TIMEOUT_SECONDS = 3_600.0
M6B_BUILDER_TIMEOUT_SECONDS = 10_800.0
M6B_ONLINE_TIMEOUT_SECONDS = 10_800.0
M6B_SWAP_LIMIT_BYTES = 0
M6B_PREDICTED_LIVE_SET_LIMIT_BYTES = 1_750_000_000
M6B_FACTOR_PAYLOAD_BYTES = 84 * (882 * 882 * 16 + 882 * 4)
M6B_SHIFTED_STORE_METADATA_RESERVE_BYTES = 8_000_000
M6B_M5_PEAK_MINUS_M3Y_BYTES = 978_083_840 - 525_196_562
M6B_M6A_RETAINED_WORK_BYTES = 16_673_350
M6B_ONE_TRANSIENT_FACTOR_BYTES = 882 * 882 * 16 + 882 * 4
M6B_SECOND_VOLUME_ACTION_RESERVE_BYTES = 64_000_000
M6B_FIXED_RUNTIME_RESERVE_BYTES = 64_000_000
M6B_PREDICTED_LIVE_SET_BYTES = sum(
    (
        M6B_M5_PEAK_MINUS_M3Y_BYTES,
        M6B_FACTOR_PAYLOAD_BYTES,
        M6B_SHIFTED_STORE_METADATA_RESERVE_BYTES,
        M6B_M6A_RETAINED_WORK_BYTES,
        M6B_ONE_TRANSIENT_FACTOR_BYTES,
        M6B_SECOND_VOLUME_ACTION_RESERVE_BYTES,
        M6B_FIXED_RUNTIME_RESERVE_BYTES,
    )
)
M6B_W1_SCHEMA = "task037.extra.m6b.sparse-range-builder.v2"
M6B_W1_BASE_PREDICTED_LIVE_SET_BYTES = 1_657_665_813
M6B_W1_PREDICTED_LIVE_SET_LIMIT_BYTES = 1_750_000_000
M6B_W1_BUILDER_RSS_LIMIT_BYTES = 1_500_000_000
M6B_W2_SCHEMA = "task037.extra.m6b.local-range-diagnostic.v1"
M6B_W2_SHIFTED_BETA = 1.0
M6B_W2_FIXED_RESIDUAL_ITERATIONS = (20, 100, 150, 200)
M6B_W2_FACTOR_MANIFEST_SHA256 = (
    "5394db24e96f611870c104fe7367e15163cb89a2943cd455f5c69e39eadf7363"
)
M6B_W2_RESIDUAL_SOURCE_SHA = (
    "d98254fecddc41940f50f72753ec9f0f80407793"
)
M6B_W2_W0_OUTPUT_SHA256 = (
    "acef3e163057fb60db50e9362d9303a8275555a93027258bfbbbc4b001ff3568"
)
M6B_W2_W0_ORACLE_SOURCE_SHA = (
    "5e7f9d42eaf994440655fde9f79eb85e2f2745b9"
)
M6B_W2_W0_BASIS_MANIFEST_SHA256 = (
    "ce3e38f7fa8be3dc704163d744eee8cecc3265b5872664d893b990c2845b765c"
)
M6B_W2_W0_AZ_COLUMN_SHA256_AGGREGATE = (
    "4eaee22f49fcac7546e93fdc59237949579e93c20af604eefd396c4f7fedccce"
)
M6B_W2_WAVE_MANIFEST_SHA256 = (
    "5052b8988ae58107afcdc1bc792aef377b4bd12f598376e1c4089b148ef62d78"
)
M6B_W2_WAVE_SOURCE_SHA = "e2f99a38d9ba2c7b26ca6cdb37a1a4f9310aebfd"
M6B_W2_JIT_INVENTORY_SHA256 = (
    "89b34d252e15883d675fe37e207578d93310a1b43516dc6f4280923c46f6f688"
)
M6B_W2_RESIDUAL_ARRAY_SHAS = {
    "20": "5901f92d16d5dec20aeb4b5fed61768f639f9fd8072061e3f29ade7e39301070",
    "100": "0ff1d3badbe98c1d33ac2d4c6ddfe1d8a40ca2986ef414bb42282228cd8b630c",
    "150": "1185adf461814c1dce932433ab9bafaccfcfa4217ea130e638b30fad1560db17",
    "200": "16c86eaf01d7eef9f02f51b27ae120e5c9c5ae00c56e5426b8e6a8e56d568ed3",
}
M6B_W2_RANGE_RHO_AUTHORITY = {
    "20": 0.8502163662584745,
    "100": 0.8663708224767056,
    "150": 0.8671486245194239,
    "200": 0.8665579730254086,
}
M6B_W2_W0_RANGE_RHO_AUTHORITY = M6B_W2_RANGE_RHO_AUTHORITY
M6B_W2_BASE_PREDICTED_LIVE_SET_BYTES = 1_698_273_595
M6B_W2_EXTERNAL_RESIDUAL_BYTES = 2_780_832
M6B_W2_COMPOSITION_INCREMENTAL_BYTES = 5_561_664
M6B_W2_PREDICTED_LIVE_SET_BYTES = (
    M6B_W2_BASE_PREDICTED_LIVE_SET_BYTES
    + M6B_W2_EXTERNAL_RESIDUAL_BYTES
    + M6B_W2_COMPOSITION_INCREMENTAL_BYTES
)
M6B_W2_PREDICTED_LIVE_SET_LIMIT_BYTES = 1_750_000_000
M6B_W2R_SCHEMA = "task037.extra.m6b.projected-range-diagnostic.v1"
M6B_W2R_BASE_PREDICTED_LIVE_SET_BYTES = 1_698_273_595
M6B_W2R_FULL_VECTOR_BYTES = M6B_GLOBAL_ROWS * 16
M6B_W2R_PROJECTED_FULL_VECTOR_COUNT = 8
M6B_W2R_EXTERNAL_RESIDUAL_BYTES = 2_780_832
M6B_W2R_PROJECTED_INCREMENTAL_BYTES = (
    M6B_W2R_PROJECTED_FULL_VECTOR_COUNT * M6B_W2R_FULL_VECTOR_BYTES
)
M6B_W2R_PREDICTED_LIVE_SET_BYTES = (
    M6B_W2R_BASE_PREDICTED_LIVE_SET_BYTES
    + M6B_W2R_EXTERNAL_RESIDUAL_BYTES
    + M6B_W2R_PROJECTED_INCREMENTAL_BYTES
)
M6B_W2R_PREDICTED_LIVE_SET_LIMIT_BYTES = 1_750_000_000
M6B_W3_SCHEMA = "task037.extra.m6b.fixed-time-harmonic-screen.v1"
M6B_W3_PHASE = "w3_screen"
M6B_W3_BETA = 1.0
M6B_W3_BETA05_SCHEMA = (
    "task037.extra.m6b.fixed-time-harmonic-screen-beta05.v1"
)
M6B_W3_BETA05_PHASE = "w3_beta05_screen"
M6B_W3_BETA05 = 0.5
M6B_W3_BETA05_FACTOR_MANIFEST_SHA256 = (
    "0d9ef8c8ad788c6f8f037d01054a9e21c091ebe68595ebbf77aaef496289f823"
)
M6B_W3_BETA05_FACTOR_SOURCE_SHA = (
    "2a0c279cf953cc4ac34a18a4c24dfc2c009ada56"
)
M6B_W3_COMPACT_PATH = (
    "benchmarks/cases/101_task37_extra_development/records/"
    "m6b_w2r_projected_range_diagnostic.json"
)
M6B_W3_COMPACT_FILE_SHA256 = (
    "00c24c9ee08f7151f905b5fd53367a6be978b721407ee135bf9f68bec89eb9cb"
)
M6B_W3_W2R_SOURCE_SHA = "1cdcb19ac5b96c8bf5b3dd8633a01a67bbc81b45"
M6B_W3_RESTART = 20
M6B_W3_MAX_IT = 200
M6B_W4_SCHEMA = "task037.extra.m6b.fixed-time-harmonic-fbcgs-screen.v1"
M6B_W4_PHASE = "w4_fbcgs_screen"
M6B_W4_BETA = 1.0
M6B_W4_KSP_ITERATIONS = (10, 50, 75, 100)
M6B_W4_PC_APPLY_BUDGETS = (20, 100, 150, 200)
M6B_W4_KSP_TO_PC_BUDGET = dict(
    zip(M6B_W4_KSP_ITERATIONS, M6B_W4_PC_APPLY_BUDGETS)
)
M6B_W4_PREDICTED_LIVE_SET_BYTES = 1_723_301_083
M6B_W4_PREDICTED_LIVE_SET_LIMIT_BYTES = 1_750_000_000
M6B_W5_SCHEMA = "task037.extra.m6b.disk-fgmres-screen.v1"
M6B_W5_CORE_SCHEMA = "task037.extra.h2b.m6b.disk-fgmres-screen.v1"
M6B_W5_CHECK_SCHEMA = "task037.extra.m6b.disk-fgmres-screen.check.v1"
M6B_W5_PHASE = "w5_disk_fgmres_screen"
M6B_W5_BETA = 1.0
M6B_W5_STEADY_CALIBRATION_BYTES = 1_599_762_432
M6B_W5_CORE_INCREMENT_BYTES = 67_108_864
M6B_W5_PREDICTED_LIVE_SET_BYTES = (
    M6B_W5_STEADY_CALIBRATION_BYTES + M6B_W5_CORE_INCREMENT_BYTES
)
M6B_W5_SCRATCH_V_BYTES = 558_947_232
M6B_W5_SCRATCH_Z_BYTES = 556_166_400
M6B_W5_SCRATCH_BYTES = 1_115_113_632
M6B_W5_FULL_VECTOR_BUFFER_LIMIT_BYTES = 64 * 1024 * 1024
M6B_W5_EXPECTED_PROCESS_PEAK_BYTES = 1_607_802_880
M6B_W5_RAW_ARTIFACT_NAMES = tuple(
    [
        "m6b_w5_summary.json",
        "m6b_w5_progress.jsonl",
    ]
    + [
        f"m6b_iter{iteration}_{name}.npy"
        for iteration in (20, 100, 150, 200)
        for name in ("solution", "outer_action", "residual", "rhs")
    ]
)
M6B_W5_WATCHDOG_ARTIFACT_NAMES = (
    "w5_disk_fgmres_screen_root_pid.json",
    "w5_disk_fgmres_screen_stdout.txt",
    "w5_disk_fgmres_screen_timeline.jsonl",
)
M6B_W7_S1_SCHEMA = "task037.extra.m6b.w7-s1.restart-disk-fgmres-screen.v1"
M6B_W7_S1_CORE_SCHEMA = (
    "task037.extra.h2b.m6b.w7-s1.restart-disk-fgmres-screen.v1"
)
M6B_W7_S1_CHECK_SCHEMA = (
    "task037.extra.m6b.w7-s1.restart-disk-fgmres-screen.check.v1"
)
M6B_W7_S1_PHASE = "w7_s1_restart_disk_fgmres_screen"
M6B_W7_S1_TIMEOUT_SECONDS = 10_800.0
M6B_W7_S1_LOCAL_ITERATIONS = (20, 100, 150, 200)
M6B_W7_S1_CUMULATIVE_ITERATIONS = (220, 300, 350, 400)
M6B_W7_S1_W5_COMPACT_RELATIVE_PATH = (
    "benchmarks/cases/101_task37_extra_development/records/"
    "m6b_w5_disk_fgmres_screen.json"
)
M6B_W7_S1_W5_COMPACT_FILE_SHA256 = (
    "fa9d92d84ba010a6f5f8effd18b0205e8d1b592382f3633b247a65fe8dbf91e5"
)
M6B_W7_S1_W5_SOURCE_SHA = (
    "41cbbd454eb8336d9ea5378ed618447acfc60aac"
)
M6B_W7_S1_INITIAL_RHO = 0.12750559935416836
M6B_W7_S1_PREDICTED_LIVE_SET_LIMIT_BYTES = 1_750_000_000
M6B_W7_S1_W5_CALIBRATED_PEAK_BYTES = 1_608_527_872
M6B_W7_S1_RAW_ARTIFACT_NAMES = tuple(
    ["m6b_w7_s1_summary.json", "m6b_w7_s1_progress.jsonl"]
    + [
        f"m6b_iter{iteration}_{name}.npy"
        for iteration in M6B_W7_S1_LOCAL_ITERATIONS
        for name in ("solution", "outer_action", "residual", "rhs")
    ]
)
M6B_W7_S1_WATCHDOG_ARTIFACT_NAMES = (
    "w7_s1_restart_disk_fgmres_screen_root_pid.json",
    "w7_s1_restart_disk_fgmres_screen_stdout.txt",
    "w7_s1_restart_disk_fgmres_screen_timeline.jsonl",
)
M6B_W6A_SCHEMA = "task037.extra.m6b.w6a.multi-order-range.builder.v1"
M6B_W6A_PHASE = "w6a_multi_order_range_builder"
M6B_W6A_CORE_SCHEMA = "task037.extra.m6b.w6a.multi-order-range.v1"
M6B_W6A_LEGACY_COLUMNS = 75
M6B_W6A_ADDED_COLUMNS = 315
M6B_W6A_COLUMNS = 390
M6B_W6A_ORDERS = (-7, -6, -5, -4, -3, -2, -1)
M6B_W6A_Z_PLANES = 15
M6B_W6A_COMPONENTS = 3
M6B_W6A_NORMAL_CLOSURE_LIMIT = 1.0e-11
M6B_W6A_RHO_LIMIT = 0.70
M6B_W6A_IMPROVEMENT_LIMIT = 0.15
M6B_W6A_PREDICTED_LIVE_SET_LIMIT_BYTES = 1_750_000_000
M6B_W6A_REPEAT_COLUMNS = (0, 74, 75, 389)
M6B_W6A_BUILDER_TIMEOUT_SECONDS = 7_200.0
M6B_W6A_WATCHDOG_RSS_LIMIT_BYTES = 1_950_000_000
M6B_W6A_BUILDER_RSS_LIMIT_BYTES = 1_750_000_000
M6B_W6A_WATCHDOG_SCHEMA = "task037.extra.m6b.w6a.watchdog.v1"
M6B_W6A_FORMAL_CHECK_SCHEMA = "task037.extra.m6b.w6a.formal-check.v1"
M6B_W6A_JIT_INVENTORY_SHA256 = (
    "89b34d252e15883d675fe37e207578d93310a1b43516dc6f4280923c46f6f688"
)
M6B_W6A_W5_RESIDUAL_ITERATIONS = (20, 100, 150, 200)
M6B_W6A_W5_COMPACT_RELATIVE_PATH = (
    "benchmarks/cases/101_task37_extra_development/records/"
    "m6b_w5_disk_fgmres_screen.json"
)
M6B_W6A_W5_SOURCE_SHA = "41cbbd454eb8336d9ea5378ed618447acfc60aac"
M6B_W6A_W5_COMPACT_FILE_SHA256 = (
    "fa9d92d84ba010a6f5f8effd18b0205e8d1b592382f3633b247a65fe8dbf91e5"
)
M6B_W6B_S0_W6A_SUMMARY_FILE_SHA256 = (
    "b90cda13e46dedcc853387a65ba94882405f90cf7abeea0e32ef949751a7acbd"
)
M6B_W6B_S0_W6A_PRODUCER_SOURCE_SHA = (
    "21982b739deac94d80a5048c58f5dabd96d434bd"
)
M6B_W6A_MANIFEST_RESERVE_BYTES = 1_000_000
M6B_W8A_SCHEMA = "task037.extra.m6b.w8a.z-bubble-range.builder.v1"
M6B_W8A_PHASE = "w8a_z_bubble_range_builder"
M6B_W8A_WATCHDOG_SCHEMA = "task037.extra.m6b.w8a.watchdog.v1"
M6B_W8A_FORMAL_CHECK_SCHEMA = "task037.extra.m6b.w8a.formal-check.v1"
M6B_W8A_RECOVERY_SCHEMA = "task037.extra.m6b.w8a.post-numeric-recovery.v1"
M6B_W8A_RECOVERY_PHASE = "w8a_post_numeric_recovery"
M6B_W8A_RECOVERY_PRODUCER_SHA = "86c74a2b0339817a2c7756c9fde778be1f36f2e3"
M6B_W8A_RECOVERY_RAW_RELATIVE_PATH = (
    "benchmarks/artifacts/task037_extra_development/"
    "m6b_w8a_86c74a2_builder_run1"
)
M6B_W8A_RECOVERY_WATCHDOG_PATH = "/tmp/task037_m6b_w8a_86c74a2_watchdog_run1"
M6B_W8A_RECOVERY_WATCHDOG_SUMMARY_SHA256 = (
    "5e4f0d4b9b8227215b1e2144a676ed4eb81faa1c8e5398d3fbf683e1eb15aba0"
)
M6B_W8A_RECOVERY_RAW_FILE_SHA256 = {
    "w8a_progress.jsonl": "e702f68c94fc286f1e185a7908d8fc8dfcfb8aedf334fc7f504ae22bb0ef2cc5",
    "sparse_range_store/manifest.json": "2e18282bc07d53acaa96255bec74e0afa33d0a146b774005427b6e0704f2404a",
    "sparse_range_store/z_data.npy": "1a7d2a15fd9d8e43f7566727ffa9542802c42600fc0ef004b6380f3fa20e533c",
    "sparse_range_store/z_indices.npy": "fb62a537df6b12dae7f65268842998b266116ae4dddaeb91b461d17b159cffd9",
    "sparse_range_store/z_indptr.npy": "383f19295adf30e5c8dcbb48f3dc7a29e6c7b73fca4d5a5ef7522ce4aabee7a4",
    "sparse_range_store/gram.npy": "b6fceeaeb54f841eb560362d6e9532b5c32c9c58bec41f19e495914908783250",
    "sparse_range_store/r_factor.npy": "f23893cb0db71244095a244e61ed1732e75d88f3b247ba5c9a19ed7957032b72",
    "az_scratch/new_columns.bin": "bf1e05cf9259e06eb0c579e25960916f982f3969a646a180a8072b0594c68f26",
}
M6B_W8A_RECOVERY_WATCHDOG_FILE_SHA256 = {
    "w8a_watchdog_summary.json": M6B_W8A_RECOVERY_WATCHDOG_SUMMARY_SHA256,
    "w8a_z_bubble_range_builder_timeline.jsonl": "dd00d8d70b58232c7a78275459ce967cac561b4b027184c0d76db5ebc735ee47",
    "w8a_z_bubble_range_builder_stdout.txt": "ce4b14020b0f19cbc166ff4947a922a04cf5eea0129b4eb0b3cdeffd4ee12769",
    "w8a_z_bubble_range_builder_root_pid.json": "b3ddc2774cc0c3ba3c4a1586543e3640ec80a0b7ebe6842e65d01a0ae1cb6312",
}
M6B_W8A_COMPANION_SCHEMA = "task037.extra.m6b.w8a.companion-probe.v1"
M6B_W8A_COMPANION_PHASE = "w8a_companion_probe"
M6B_W8A_COMPANION_WATCHDOG_SCHEMA = (
    "task037.extra.m6b.w8a.companion-watchdog.v1"
)
M6B_W8A_COMPANION_TIMEOUT_SECONDS = 7_200.0
M6B_W8A_COMPANION_SENTINEL_COLUMNS = (390, 459, 529)
M6B_W8A_RECOVERY_ALLOWED_CHANGED_PATHS = frozenset({
    "benchmarks/run_task037_extra_m6b.py",
    "src/test/test_324_task037_m6b_w8_bubbles.py",
})
M6B_W8A_LEGACY_COLUMNS = 390
M6B_W8A_ADDED_COLUMNS = 140
M6B_W8A_COLUMNS = 530
M6B_W8A_ORDERS = (-7, -6)
M6B_W8A_COMPONENT = 1
M6B_W8A_INTERVALS = 14
M6B_W8A_BUBBLE_DEGREES = (2, 3, 4, 5, 6)
M6B_W8A_REPEAT_COLUMNS = (390, 459, 529)
M6B_W8A_NORMAL_CLOSURE_LIMIT = 1.0e-11
M6B_W8A_RETAINED_LIMIT_BYTES = int(0.20 * 1024**3)
M6B_W8A_PREDICTED_LIVE_SET_LIMIT_BYTES = 1_750_000_000
M6B_W8A_WATCHDOG_RSS_LIMIT_BYTES = 1_950_000_000
M6B_W8A_BUILDER_RSS_LIMIT_BYTES = 1_750_000_000
M6B_W8A_TIMEOUT_SECONDS = 7_200.0
M6B_W8A_PRODUCTION_BASE_PEAK_BYTES = M6B_W7_S1_W5_CALIBRATED_PEAK_BYTES
M6B_W8A_W6A_SUMMARY_SHA256 = M6B_W6B_S0_W6A_SUMMARY_FILE_SHA256
M6B_W8A_W6A_SOURCE_SHA = M6B_W6B_S0_W6A_PRODUCER_SOURCE_SHA
M6B_W8A_W6A_JIT_INVENTORY_SHA256 = M6B_W6A_JIT_INVENTORY_SHA256
M6B_W8A_W5_COMPACT_SHA256 = M6B_W6A_W5_COMPACT_FILE_SHA256
M6B_W8A_W5_SOURCE_SHA = M6B_W6A_W5_SOURCE_SHA
M6B_W8A_W7_COMPACT_RELATIVE_PATH = (
    "benchmarks/cases/101_task37_extra_development/records/"
    "m6b_w7_s1_restart_disk_fgmres_screen.json"
)
M6B_W8A_W7_COMPACT_SHA256 = (
    "3fcabe2dbc753017158b7f587f025a73a4e5f2eb5b7539d264cd3984846a192d"
)
M6B_W8A_W7_SOURCE_SHA = "7febc1e3aeb52613d098fd2aadede3b288c69b5b"
M6B_W8B_SCHEMA = "task037.extra.m6b.w8b.offline-projection.v1"
M6B_W8B_PHASE = "w8b_offline_range_projection"
M6B_W9A_CHECK_SCHEMA = "task037.extra.m6b.w9a.checkpoint-recycle.check.v1"
M6B_W9A_PHASE = "w9a_checkpoint_recycle"
M6B_W9A_CHECKPOINTS = (20, 100, 150, 200)
M6B_W9A_NORMAL_CLOSURE_LIMIT = 1.0e-11
M6B_W9A_TARGET_RHO_LIMIT = 0.90
M6B_W9A_CONTROL_RHO_LOWER = 1.0 - 1.0e-10
M6B_W9A_CONTROL_RHO_UPPER = 1.0 + 1.0e-10
M6B_W9A_CONTROL_CAPTURED_ENERGY_LIMIT = 2.0e-10
M6B_W10A_CHECK_SCHEMA = "task037.extra.m6b.w10a.krylov-span.check.v1"
M6B_W10A_PHASE = "w10a_krylov_span_recycle"
M6B_W10A_COLUMNS = 201
M6B_W10A_ROW_BLOCK = 4096
M6B_W10A_BASIS_RELATIVE_PATH = "krylov_scratch/v_basis.bin"
M6B_W10A_BASIS_BYTES = 558_947_232
M6B_W10A_TARGET_RHO_LIMIT = 0.90
M6B_W10A_CONTROL_RHO_LOWER = 1.0 - 1.0e-10
M6B_W6A_EVENTS = (
    "authority_validated",
    "mesh_ready",
    "space_ready",
    "floquet_mpc_ready",
    "cache_ready",
    "outer_ready",
    "legacy_basis_ready",
)
M6B_W6A_TRAILING_EVENTS = (
    "az_ready",
    "gram_ready",
    "residuals_ready",
    "summary_ready",
)
M6B_W3_PRODUCTION_ACTION_COUNT = {
    "local_apply": 1,
    "physical_outer_action": 3,
    "range_apply": 2,
}
M6B_W3_M5_100_STEP_WALL_SECONDS = 1185.652239
M6B_W3_W2R_FOUR_DIAGNOSTIC_WALL_SECONDS = 402.4505279730074
M6B_W3_DIAGNOSTIC_ACTIONS_PER_RESIDUAL = 9
M6B_W3_ITERATION_ACTION_CLASSES = sum(M6B_W3_PRODUCTION_ACTION_COUNT.values()) + 1
M6B_W3_FULL_VECTOR_BYTES = M6B_GLOBAL_ROWS * 16
M6B_W3_FGMRES_V_VECTORS = M6B_W3_RESTART + 1
M6B_W3_FGMRES_Z_VECTORS = M6B_W3_RESTART
M6B_W3_FGMRES_V_BYTES = M6B_W3_FGMRES_V_VECTORS * M6B_W3_FULL_VECTOR_BYTES
M6B_W3_FGMRES_Z_BYTES = M6B_W3_FGMRES_Z_VECTORS * M6B_W3_FULL_VECTOR_BYTES
M6B_W3_FGMRES_THEORETICAL_BYTES = M6B_W3_FGMRES_V_BYTES + M6B_W3_FGMRES_Z_BYTES
M6B_W3_INHERITED_RESERVE_BYTES = M6B_FIXED_RUNTIME_RESERVE_BYTES
# The W2R/W1A base is calibrated from the M5 restart=20 FGMRES process peak;
# the V(m+1) and flexible Z(m) vectors are therefore lifecycle evidence already
# covered by that base, not an additive second copy in this prediction.
M6B_W3_UNCOVERED_KRYLOV_BYTES = 0
M6B_W3_PREDICTED_LIVE_SET_BYTES = (
    M6B_W2R_PREDICTED_LIVE_SET_BYTES + M6B_W3_UNCOVERED_KRYLOV_BYTES
)
M6B_W3_PREDICTED_LIVE_SET_LIMIT_BYTES = 1_750_000_000
M6B_W3_RUNTIME_TIMEOUT_SECONDS = 19_200.0
M6B_W2R_OLD_NEGATIVE_SOURCE_SHA = (
    "64e479404ce30384e49aad58ada573fb9cdf8d62"
)
M6B_W2R_OLD_RAW_SUMMARY_SHA256 = (
    "009f00990c85f27eb3ae01b449662fdb66b897f8e2191b55f4d42a9051846678"
)
M6B_W2R_OLD_WATCHDOG_SUMMARY_SHA256 = (
    "eadfc56a5e4f2ddac4988532dfd4f44533d8ad9c7215e5dbe957ff03cf2a14b1"
)
M6B_W2R_OLD_NEGATIVE_PEAK_RSS_BYTES = 1_591_648_256
M6B_STAGE_EVENTS = (
    "authority_validated",
    "mesh_ready",
    "space_ready",
    "floquet_mpc_ready",
    "proxy_forms_ready",
    "outer_form_ready",
    "shifted_form_ready",
    "surface_forms_ready",
    "summary_ready",
)
M6B_BUILDER_EVENTS = (
    "authority_validated",
    "mesh_ready",
    "space_ready",
    "floquet_mpc_ready",
    "class_expansion_ready",
    "class_blocks_ready",
    "neighborhood_ready",
    "patch_stream_ready",
    "factor_store_ready",
    "summary_ready",
)
M6B_ONLINE_EVENTS = (
    "authority_validated",
    "mesh_ready",
    "space_ready",
    "floquet_mpc_ready",
    "cache_ready",
    "store_ready",
    "outer_action_ready",
    "rhs_ready",
    "screen_ready",
    "summary_ready",
)
M6B_SCREEN_ITERATIONS = (20, 100, 150, 200)
M6B_SCREEN_RHO_LIMITS = {
    "20": 0.60,
    "100": 0.20,
    "200": 0.08,
}
M6B_IMPROVEMENT_LIMIT = 0.15


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _attach_evidence(value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    result.pop("evidence_sha256", None)
    result["evidence_sha256"] = hashlib.sha256(_canonical_json(result)).hexdigest()
    return result


def _evidence_valid(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    observed = value.get("evidence_sha256")
    return (
        isinstance(observed, str)
        and len(observed) == 64
        and observed == _attach_evidence(value).get("evidence_sha256")
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact(root: Path, relative: str) -> dict[str, Any]:
    path = root / relative
    if not path.is_file():
        return {"path": relative, "present": False}
    return {
        "path": relative,
        "present": True,
        "bytes": int(path.stat().st_size),
        "sha256": _sha256_file(path),
    }


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n",
        encoding="utf-8",
    )


def _m6b_scope(*, phase: str | None = None) -> dict[str, Any]:
    scope: dict[str, Any] = {
        "degree": M6B_DEGREE,
        "h_nm": M6B_H_NM,
        "global_cells": M6B_GLOBAL_CELLS,
        "local_nloc": M6B_LOCAL_NLOC,
        "global_rows": M6B_GLOBAL_ROWS,
        "constraint_count": M6B_CONSTRAINTS,
        "beta": M6B_BETA,
        "factor_count": M6B_FACTOR_COUNT,
        "factor_reuse_count": M6B_FACTOR_REUSE,
        "operator": "A=Kcurl-k0^2*M_epsilon+A_DtN",
        "shifted_operator": M6B_SHIFTED_OPERATOR,
        "fine_space": "uncondensed_fullspace",
        "global_matrix": False,
        "augmented_matrix": False,
        "static_condensation": False,
        "trace_slab_pc": False,
        "ordinary_default": False,
        "watchdog_rss_limit_bytes": M6B_WATCHDOG_RSS_LIMIT_BYTES,
        "online_completion_rss_limit_bytes": M6B_ONLINE_COMPLETION_RSS_LIMIT_BYTES,
        "stage_timeout_seconds": M6B_STAGE_TIMEOUT_SECONDS,
        "builder_timeout_seconds": M6B_BUILDER_TIMEOUT_SECONDS,
        "online_timeout_seconds": M6B_ONLINE_TIMEOUT_SECONDS,
        "timeout_basis": (
            "M5 100-step measured wall plus shifted-LU one-PC timing; "
            "online budget is fixed at 10800 seconds"
        ),
        "swap_limit_bytes": M6B_SWAP_LIMIT_BYTES,
        "predicted_live_set_bytes": M6B_PREDICTED_LIVE_SET_BYTES,
        "predicted_live_set_limit_bytes": M6B_PREDICTED_LIVE_SET_LIMIT_BYTES,
        "predicted_live_set_is_measurement": False,
        "predicted_live_set_basis": {
            "m5_online_peak_minus_m3y_retained_bytes": M6B_M5_PEAK_MINUS_M3Y_BYTES,
            "shifted_factor_payload_bytes": M6B_FACTOR_PAYLOAD_BYTES,
            "shifted_store_metadata_reserve_bytes": M6B_SHIFTED_STORE_METADATA_RESERVE_BYTES,
            "m6a_retained_plus_work_bytes": M6B_M6A_RETAINED_WORK_BYTES,
            "one_transient_factor_bytes": M6B_ONE_TRANSIENT_FACTOR_BYTES,
            "second_volume_action_reserve_bytes": M6B_SECOND_VOLUME_ACTION_RESERVE_BYTES,
            "fixed_runtime_reserve_bytes": M6B_FIXED_RUNTIME_RESERVE_BYTES,
        },
        "screen_iterations": list(M6B_SCREEN_ITERATIONS),
        "screen_rho_limits": dict(M6B_SCREEN_RHO_LIMITS),
        "screen_improvement_limit": M6B_IMPROVEMENT_LIMIT,
        "retained_total_limit_bytes": M6B_RETAINED_TOTAL_LIMIT_BYTES,
        "physical_rhs_definition": (
            "fresh M6A incident top traction plus fixed modal projections"
        ),
    }
    if phase is not None:
        scope["phase"] = str(phase)
    return scope


def _predicted_live_set() -> dict[str, Any]:
    components = {
        "m5_online_peak_minus_m3y_retained_bytes": M6B_M5_PEAK_MINUS_M3Y_BYTES,
        "shifted_lu_factor_payload_bytes": M6B_FACTOR_PAYLOAD_BYTES,
        "shifted_store_metadata_reserve_bytes": M6B_SHIFTED_STORE_METADATA_RESERVE_BYTES,
        "m6a_retained_plus_work_bytes": M6B_M6A_RETAINED_WORK_BYTES,
        "one_transient_factor_bytes": M6B_ONE_TRANSIENT_FACTOR_BYTES,
        "second_volume_action_reserve_bytes": M6B_SECOND_VOLUME_ACTION_RESERVE_BYTES,
        "fixed_runtime_reserve_bytes": M6B_FIXED_RUNTIME_RESERVE_BYTES,
    }
    total = int(sum(components.values()))
    return {
        "components": components,
        "predicted_live_set_bytes": total,
        "limit_bytes": M6B_PREDICTED_LIVE_SET_LIMIT_BYTES,
        "gate": total <= M6B_PREDICTED_LIVE_SET_LIMIT_BYTES,
        "is_measurement": False,
    }


def _dynamic_predicted_live_set(retained_total_bytes: int) -> dict[str, Any]:
    if type(retained_total_bytes) is not int or retained_total_bytes < 0:
        raise ValueError("M6B retained store total is invalid")
    components = dict(_predicted_live_set()["components"])
    del components["shifted_lu_factor_payload_bytes"]
    del components["shifted_store_metadata_reserve_bytes"]
    components["shifted_store_retained_total_bytes"] = retained_total_bytes
    total = int(sum(components.values()))
    return {
        "components": components,
        "predicted_live_set_bytes": total,
        "limit_bytes": M6B_PREDICTED_LIVE_SET_LIMIT_BYTES,
        "gate": total <= M6B_PREDICTED_LIVE_SET_LIMIT_BYTES,
        "is_measurement": False,
        "basis": "builder factor_audit.retained_total_bytes",
    }


def _finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _m6b_w2_scope(*, phase: str = "w2_diagnostic") -> dict[str, Any]:
    return {
        "degree": M6B_DEGREE,
        "h_nm": M6B_H_NM,
        "global_cells": M6B_GLOBAL_CELLS,
        "local_cells": M6B_GLOBAL_CELLS,
        "local_nloc": M6B_LOCAL_NLOC,
        "global_rows": M6B_GLOBAL_ROWS,
        "constraint_count": M6B_CONSTRAINTS,
        "factor_count": M6B_FACTOR_COUNT,
        "factor_reuse_count": M6B_FACTOR_REUSE,
        "beta": M6B_W2_SHIFTED_BETA,
        "operator": "A=Kcurl-k0^2*M_epsilon+A_DtN",
        "shifted_operator": M6B_SHIFTED_OPERATOR,
        "fine_space": "uncondensed_fullspace",
        "global_matrix": False,
        "static_condensation": False,
        "trace_slab_pc": False,
        "ordinary_default": False,
        "mpi_size": 1,
        "fixed_order": "local_then_physical_residual_then_range",
        "scan": False,
        "phase": phase,
    }


def _m6b_w2r_scope(*, phase: str = "w2r_diagnostic") -> dict[str, Any]:
    scope = _m6b_w2_scope(phase=phase)
    scope.update(
        {
            "fixed_order": "projected_range_complement",
            "production_action_counts": {
                "local_apply": 1,
                "physical_outer_action": 3,
                "range_apply": 2,
            },
            "projected_full_vector_count": M6B_W2R_PROJECTED_FULL_VECTOR_COUNT,
            "predicted_live_set_bytes": M6B_W2R_PREDICTED_LIVE_SET_BYTES,
            "predicted_live_set_limit_bytes": M6B_W2R_PREDICTED_LIVE_SET_LIMIT_BYTES,
            "predicted_live_set_is_measurement": False,
        }
    )
    return scope


def _m6b_w2r_predicted_live_set() -> dict[str, Any]:
    components = {
        "w1a_base_predicted_live_set_bytes": M6B_W2R_BASE_PREDICTED_LIVE_SET_BYTES,
        "one_external_residual_bytes": M6B_W2R_EXTERNAL_RESIDUAL_BYTES,
        "projected_full_vector_incremental_bytes": (
            M6B_W2R_PROJECTED_INCREMENTAL_BYTES
        ),
    }
    total = int(sum(components.values()))
    return {
        "components": components,
        "full_vector_bytes": M6B_W2R_FULL_VECTOR_BYTES,
        "projected_full_vector_count": M6B_W2R_PROJECTED_FULL_VECTOR_COUNT,
        "predicted_live_set_bytes": total,
        "limit_bytes": M6B_W2R_PREDICTED_LIVE_SET_LIMIT_BYTES,
        "gate": total <= M6B_W2R_PREDICTED_LIVE_SET_LIMIT_BYTES,
        "is_measurement": False,
        "derived_not_measured": True,
        "prediction_scope": "production_apply_not_diagnostic_measurement",
        "phase_lifecycle": {
            "local_and_projection": "local plus projected range vectors",
            "conservative_peak_full_vectors": M6B_W2R_PROJECTED_FULL_VECTOR_COUNT,
            "incremental_bytes": M6B_W2R_PROJECTED_INCREMENTAL_BYTES,
            "dtn_base_reserve_in_base": True,
        },
        "basis": "W1A base plus external residual and eight full-space vectors",
    }


def _m6b_w3_runtime_prediction() -> dict[str, Any]:
    conservative_w3_iteration_seconds = (
        M6B_W3_W2R_FOUR_DIAGNOSTIC_WALL_SECONDS / 4.0
        * M6B_W3_ITERATION_ACTION_CLASSES
        / M6B_W3_DIAGNOSTIC_ACTIONS_PER_RESIDUAL
    )
    scaled_w3_seconds = 200.0 * conservative_w3_iteration_seconds
    scaled_m5_seconds = 2.0 * M6B_W3_M5_100_STEP_WALL_SECONDS
    derived_seconds = max(scaled_w3_seconds, scaled_m5_seconds)
    timeout_seconds = math.ceil(1.2 * derived_seconds / 600.0) * 600.0
    if timeout_seconds != M6B_W3_RUNTIME_TIMEOUT_SECONDS:
        raise AssertionError("M6B W3 runtime authority is inconsistent")
    return {
        "m5_100_step_wall_seconds": M6B_W3_M5_100_STEP_WALL_SECONDS,
        "w2r_four_diagnostic_wall_seconds": M6B_W3_W2R_FOUR_DIAGNOSTIC_WALL_SECONDS,
        "conservative_w3_iteration_seconds": conservative_w3_iteration_seconds,
        "scaled_m5_200_step_seconds": scaled_m5_seconds,
        "scaled_w3_200_iteration_seconds": scaled_w3_seconds,
        "action_classes_per_iteration": M6B_W3_ITERATION_ACTION_CLASSES,
        "action_class_basis": (
            "one outer A plus six projected-PC actions; the two range actions "
            "include the A^H modal projection"
        ),
        "reserve_fraction": 1.2,
        "derived_timeout_seconds": timeout_seconds,
        "w2r_wall_basis": {
            "two_diagnostic_repeats_per_residual": True,
            "checkpoint_pair_wall_included_as_reserve": True,
            "derived_not_measurement": True,
        },
        "prediction_not_measurement": True,
    }


def _m6b_w3_predicted_live_set() -> dict[str, Any]:
    inherited = _m6b_w2r_predicted_live_set()
    components = {
        "w2r_production_live_set_bytes": M6B_W2R_PREDICTED_LIVE_SET_BYTES,
        "w3_uncovered_incremental_bytes": M6B_W3_UNCOVERED_KRYLOV_BYTES,
    }
    total = int(M6B_W3_PREDICTED_LIVE_SET_BYTES)
    return {
        "components": components,
        "predicted_live_set_bytes": total,
        "limit_bytes": M6B_W3_PREDICTED_LIVE_SET_LIMIT_BYTES,
        "gate": total <= M6B_W3_PREDICTED_LIVE_SET_LIMIT_BYTES,
        "derived_not_measured": True,
        "is_measurement": False,
        "prediction_scope": "production_screen_not_diagnostic_measurement",
        "restart_set": M6B_W3_RESTART,
        "fgmres_v_vectors": M6B_W3_FGMRES_V_VECTORS,
        "fgmres_z_vectors": M6B_W3_FGMRES_Z_VECTORS,
        "fgmres_v_bytes": M6B_W3_FGMRES_V_BYTES,
        "fgmres_z_bytes": M6B_W3_FGMRES_Z_BYTES,
        "fgmres_theoretical_bytes": M6B_W3_FGMRES_THEORETICAL_BYTES,
        "fgmres_lifecycle_calibrated_in_w2r_base": True,
        "inherited_fixed_runtime_reserve_bytes": M6B_W3_INHERITED_RESERVE_BYTES,
        "no_double_count": True,
        "inherited_w2r_components": inherited["components"],
        "inherited_range_store_dtn_and_external_residual": True,
    }


def _m6b_w3_scope(
    *, phase: str | None = None, shifted_beta: float = M6B_W3_BETA
) -> dict[str, Any]:
    expected_phase = (
        M6B_W3_PHASE
        if shifted_beta == M6B_W3_BETA
        else M6B_W3_BETA05_PHASE
        if shifted_beta == M6B_W3_BETA05
        else None
    )
    if expected_phase is None or (phase is not None and phase != expected_phase):
        raise ValueError("M6B W3 screen beta/phase pair is not fixed")
    phase = expected_phase
    return {
        "degree": M6B_DEGREE,
        "h_nm": M6B_H_NM,
        "global_cells": M6B_GLOBAL_CELLS,
        "local_cells": M6B_GLOBAL_CELLS,
        "local_nloc": M6B_LOCAL_NLOC,
        "global_rows": M6B_GLOBAL_ROWS,
        "constraint_count": M6B_CONSTRAINTS,
        "beta": shifted_beta,
        "factor_count": M6B_FACTOR_COUNT,
        "factor_reuse_count": M6B_FACTOR_REUSE,
        "operator": "A=Kcurl-k0^2*M_epsilon+A_DtN",
        "shifted_operator": M6B_SHIFTED_OPERATOR,
        "fine_space": "uncondensed_fullspace",
        "global_matrix": False,
        "static_condensation": False,
        "trace_slab_pc": False,
        "ordinary_default": False,
        "mpi_size": 1,
        "phase": phase,
        "fixed_order": "right_fgmres_with_projected_range_pc",
        "scan": False,
        "screen_iterations": list(M6B_SCREEN_ITERATIONS),
        "screen_rho_limits": dict(M6B_SCREEN_RHO_LIMITS),
        "screen_improvement_limit": M6B_IMPROVEMENT_LIMIT,
        "restart_set": M6B_W3_RESTART,
        "max_it": M6B_W3_MAX_IT,
        "rtol": 0.0,
        "atol": 0.0,
        "norm_type": "unpreconditioned",
        "pc_side": "right",
        "production_action_counts": dict(M6B_W3_PRODUCTION_ACTION_COUNT),
        "predicted_live_set": _m6b_w3_predicted_live_set(),
        "runtime_prediction": _m6b_w3_runtime_prediction(),
        "formal_pass": False,
        "pde_pass": False,
    }


def _m6b_w4_predicted_live_set() -> dict[str, Any]:
    inherited = _m6b_w3_predicted_live_set()
    return {
        "components": dict(inherited["components"]),
        "predicted_live_set_bytes": M6B_W4_PREDICTED_LIVE_SET_BYTES,
        "limit_bytes": M6B_W4_PREDICTED_LIVE_SET_LIMIT_BYTES,
        "gate": M6B_W4_PREDICTED_LIVE_SET_BYTES
        <= M6B_W4_PREDICTED_LIVE_SET_LIMIT_BYTES,
        "derived_not_measured": True,
        "is_measurement": False,
        "prediction_scope": "production_fbcgs_screen_not_diagnostic_measurement",
        "solver": "fbcgs",
        "restart": "not_applicable_fixed_fbcgs",
        "lifecycle_bound_reused_from_w3": True,
        "inherited_w3_bound_bytes": inherited["predicted_live_set_bytes"],
        "pde_strict_peak_limit_bytes": 2_000_000_000,
        "completion_peak_limit_bytes": M6B_ONLINE_COMPLETION_RSS_LIMIT_BYTES,
        "watchdog_peak_limit_bytes": M6B_WATCHDOG_RSS_LIMIT_BYTES,
        "swap_limit_bytes": M6B_SWAP_LIMIT_BYTES,
    }


def _m6b_w4_scope() -> dict[str, Any]:
    return {
        "schema": M6B_W4_SCHEMA,
        "degree": M6B_DEGREE,
        "h_nm": M6B_H_NM,
        "global_cells": M6B_GLOBAL_CELLS,
        "local_cells": M6B_GLOBAL_CELLS,
        "local_nloc": M6B_LOCAL_NLOC,
        "global_rows": M6B_GLOBAL_ROWS,
        "constraint_count": M6B_CONSTRAINTS,
        "beta": M6B_W4_BETA,
        "factor_count": M6B_FACTOR_COUNT,
        "factor_reuse_count": M6B_FACTOR_REUSE,
        "operator": "A=Kcurl-k0^2*M_epsilon+A_DtN",
        "shifted_operator": M6B_SHIFTED_OPERATOR,
        "fine_space": "uncondensed_fullspace",
        "global_matrix": False,
        "augmented_matrix": False,
        "static_condensation": False,
        "trace_slab_pc": False,
        "schur": False,
        "explicit_C_materialized_count": 0,
        "explicit_D_materialized_count": 0,
        "dtn_matrix_free": True,
        "ordinary_default": False,
        "mpi_size": 1,
        "phase": M6B_W4_PHASE,
        "solver": "fbcgs",
        "pc_side": "right",
        "norm_type": "unpreconditioned",
        "rtol": 0.0,
        "atol": 0.0,
        "max_it": M6B_W4_KSP_ITERATIONS[-1],
        "fixed_order": "right_fbcgs_direct_solution_vec",
        "scan": False,
        "checkpoint_axis": "pc_apply_budget",
        "monitor_solution_source": "direct_ksp_solution_vec",
        "buildSolution": False,
        "ksp_checkpoint_iterations": list(M6B_W4_KSP_ITERATIONS),
        "pc_apply_budgets": list(M6B_W4_PC_APPLY_BUDGETS),
        "ksp_iteration_to_pc_apply_budget": dict(M6B_W4_KSP_TO_PC_BUDGET),
        "screen_iterations": list(M6B_W4_PC_APPLY_BUDGETS),
        "screen_rho_limits": dict(M6B_SCREEN_RHO_LIMITS),
        "screen_improvement_limit": M6B_IMPROVEMENT_LIMIT,
        "production_action_counts": dict(M6B_W3_PRODUCTION_ACTION_COUNT),
        "predicted_live_set": _m6b_w4_predicted_live_set(),
        "formal_pass": False,
        "pde_pass": False,
    }


def _m6b_w5_predicted_live_set() -> dict[str, Any]:
    components = {
        "w4_steady_process_tree_calibration_bytes": M6B_W5_STEADY_CALIBRATION_BYTES,
        "disk_fgmres_core_full_vector_upper_bound_bytes": (
            M6B_W5_CORE_INCREMENT_BYTES
        ),
    }
    total = int(sum(components.values()))
    return {
        "components": components,
        "predicted_live_set_bytes": total,
        "limit_bytes": M6B_PREDICTED_LIVE_SET_LIMIT_BYTES,
        "gate": total <= M6B_PREDICTED_LIVE_SET_LIMIT_BYTES,
        "derived_not_measured": True,
        "is_measurement": False,
        "prediction_scope": "production_disk_fgmres_screen_not_measurement",
        "steady_calibration_source": "W4_steady_solver_process_tree",
        "w4_postsolve_fork_peak_bytes": 3_185_201_152,
        "w4_postsolve_fork_is_steady_calibration": False,
        "core_full_vector_buffer_limit_bytes": M6B_W5_FULL_VECTOR_BUFFER_LIMIT_BYTES,
        "pde_strict_peak_limit_bytes": 2_000_000_000,
        "watchdog_peak_limit_bytes": M6B_WATCHDOG_RSS_LIMIT_BYTES,
        "completion_peak_limit_bytes": M6B_ONLINE_COMPLETION_RSS_LIMIT_BYTES,
        "swap_limit_bytes": M6B_SWAP_LIMIT_BYTES,
        "scratch": {
            "v_bytes": M6B_W5_SCRATCH_V_BYTES,
            "z_bytes": M6B_W5_SCRATCH_Z_BYTES,
            "total_bytes": M6B_W5_SCRATCH_BYTES,
            "counts_as_process_rss": False,
        },
    }


def _m6b_w5_scope() -> dict[str, Any]:
    return {
        "schema": M6B_W5_SCHEMA,
        "degree": M6B_DEGREE,
        "h_nm": M6B_H_NM,
        "global_cells": M6B_GLOBAL_CELLS,
        "local_cells": M6B_GLOBAL_CELLS,
        "local_nloc": M6B_LOCAL_NLOC,
        "global_rows": M6B_GLOBAL_ROWS,
        "constraint_count": M6B_CONSTRAINTS,
        "factor_count": M6B_FACTOR_COUNT,
        "factor_reuse_count": M6B_FACTOR_REUSE,
        "beta": M6B_W5_BETA,
        "operator": "A=Kcurl-k0^2*M_epsilon+A_DtN",
        "shifted_operator": M6B_SHIFTED_OPERATOR,
        "fine_space": "uncondensed_fullspace",
        "global_matrix": False,
        "augmented_matrix": False,
        "static_condensation": False,
        "trace_slab_pc": False,
        "schur": False,
        "explicit_C_materialized_count": 0,
        "explicit_D_materialized_count": 0,
        "dtn_matrix_free": True,
        "ordinary_default": False,
        "mpi_size": 1,
        "phase": M6B_W5_PHASE,
        "solver": "disk_fgmres",
        "petsc_ksp_used": False,
        "right_side": True,
        "two_pass_mgs": True,
        "cycle": "fixed_one_200_step_cycle",
        "checkpoint_axis": "krylov_iteration",
        "screen_iterations": [20, 100, 150, 200],
        "screen_rho_limits": dict(M6B_SCREEN_RHO_LIMITS),
        "screen_improvement_limit": M6B_IMPROVEMENT_LIMIT,
        "predicted_live_set": _m6b_w5_predicted_live_set(),
        "formal_pass": False,
        "pde_pass": False,
    }


def _m6b_w7_s1_predicted_live_set() -> dict[str, Any]:
    components = {
        "w5_steady_calibration_bytes": M6B_W5_STEADY_CALIBRATION_BYTES,
        "disk_fgmres_core_full_vector_upper_bound_bytes": (
            M6B_W5_CORE_INCREMENT_BYTES
        ),
    }
    total = int(sum(components.values()))
    return {
        "components": components,
        "predicted_live_set_bytes": total,
        "limit_bytes": M6B_W7_S1_PREDICTED_LIVE_SET_LIMIT_BYTES,
        "gate": total <= M6B_W7_S1_PREDICTED_LIVE_SET_LIMIT_BYTES,
        "derived_not_measured": True,
        "is_measurement": False,
        "prediction_scope": "production_w7_s1_restart_cycle_reuses_w5_bound",
        "w5_historical_process_tree_peak_bytes": M6B_W7_S1_W5_CALIBRATED_PEAK_BYTES,
        "w5_historical_peak_is_not_prediction_component": True,
        "pde_strict_peak_limit_bytes": 2_000_000_000,
        "watchdog_peak_limit_bytes": M6B_WATCHDOG_RSS_LIMIT_BYTES,
        "completion_peak_limit_bytes": M6B_ONLINE_COMPLETION_RSS_LIMIT_BYTES,
        "swap_limit_bytes": M6B_SWAP_LIMIT_BYTES,
        "scratch": {
            "v_bytes": M6B_W5_SCRATCH_V_BYTES,
            "z_bytes": M6B_W5_SCRATCH_Z_BYTES,
            "total_bytes": M6B_W5_SCRATCH_BYTES,
            "counts_as_process_rss": False,
        },
    }


def _m6b_w7_s1_scope() -> dict[str, Any]:
    scope = _m6b_w5_scope()
    scope.update(
        {
            "schema": M6B_W7_S1_SCHEMA,
            "phase": M6B_W7_S1_PHASE,
            "solver": "disk_fgmres_restart",
            "cycle": "fixed_restart_continuation_from_w5_iter200",
            "checkpoint_axis": "local_cycle_iteration",
            "screen_iterations": list(M6B_W7_S1_LOCAL_ITERATIONS),
            "cumulative_checkpoint_iterations": list(
                M6B_W7_S1_CUMULATIVE_ITERATIONS
            ),
            "initial_solution_provided": True,
            "initial_solution_authority": "W5_iter200_solution",
            "predicted_live_set": _m6b_w7_s1_predicted_live_set(),
            "formal_pass": False,
            "pde_pass": False,
        }
    )
    return scope


def _m6b_w7_s1_numeric_gate(
    samples: Any, *, recomputed_residuals: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    required = {str(value) for value in M6B_W7_S1_LOCAL_ITERATIONS}
    checks = {
        "checkpoint_set": False,
        "local_cumulative_mapping": False,
        "finite_true_residuals": False,
        "monotone_nonincreasing": False,
        "cumulative400_le_0.08": False,
        "improvement_350_to_400_ge_0.15": False,
    }
    values: dict[str, float] = {}
    problems: list[str] = []
    if not isinstance(samples, Mapping) or set(samples) != required:
        problems.append("checkpoint_set")
    else:
        checks["checkpoint_set"] = True
        for local, cumulative in zip(
            M6B_W7_S1_LOCAL_ITERATIONS, M6B_W7_S1_CUMULATIVE_ITERATIONS
        ):
            item = samples[str(local)]
            observed = (
                recomputed_residuals.get(str(local))
                if isinstance(recomputed_residuals, Mapping)
                else item.get("true_relative_residual")
                if isinstance(item, Mapping)
                else None
            )
            if (
                not isinstance(item, Mapping)
                or item.get("iteration") != local
                or item.get("local_iteration") != local
                or item.get("cumulative_iteration") != cumulative
                or not _finite_number(observed)
                or float(observed) < 0.0
            ):
                problems.append(f"checkpoint_{local}")
                continue
            values[str(local)] = float(observed)
        checks["local_cumulative_mapping"] = not any(
            problem.startswith("checkpoint_") for problem in problems
        )
        checks["finite_true_residuals"] = set(values) == required
    if set(values) == required:
        sequence = [values[str(local)] for local in M6B_W7_S1_LOCAL_ITERATIONS]
        checks["monotone_nonincreasing"] = all(
            right <= left + 1.0e-12 for left, right in zip(sequence, sequence[1:])
        )
        # Monotonicity is retained as a diagnostic; the W7-S1 hard numeric
        # gate is the cumulative-400 residual only.
        checks["cumulative400_le_0.08"] = values["200"] <= 0.08
        if not checks["cumulative400_le_0.08"]:
            problems.append("cumulative400_true_residual")
        improvement = 1.0 - values["200"] / values["150"]
        checks["improvement_350_to_400_ge_0.15"] = bool(
            math.isfinite(improvement) and improvement >= 0.15
        )
    else:
        improvement = None
    return {
        "pass": not problems,
        "problems": sorted(set(problems)),
        "true_residuals": values,
        "cumulative_true_residuals": {
            str(cumulative): values[str(local)]
            for local, cumulative in zip(
                M6B_W7_S1_LOCAL_ITERATIONS,
                M6B_W7_S1_CUMULATIVE_ITERATIONS,
            )
            if str(local) in values
        },
        "improvement_350_to_400": improvement,
        "checks": checks,
        "limits": {
            "cumulative400_true_residual": 0.08,
            "improvement_350_to_400": 0.15,
        },
    }


def _m6b_w7_s1_load_w5_authority(
    compact_path: Path, w5_raw_dir: Path
) -> dict[str, Any]:
    import numpy as np

    compact_path = Path(compact_path).resolve()
    w5_raw_dir = Path(w5_raw_dir).resolve()
    expected_compact = (ROOT / M6B_W7_S1_W5_COMPACT_RELATIVE_PATH).resolve()
    if compact_path != expected_compact:
        raise ValueError("W7-S1 W5 compact path is not the frozen authority")
    compact_artifact = _artifact(ROOT, M6B_W7_S1_W5_COMPACT_RELATIVE_PATH)
    compact = _read_json(compact_path)
    if not (
        compact_artifact.get("present") is True
        and compact_artifact.get("sha256") == M6B_W7_S1_W5_COMPACT_FILE_SHA256
        and _evidence_valid(compact)
        and compact.get("classification") == "NUMERIC_FAIL"
        and compact.get("producer_source_sha") == M6B_W7_S1_W5_SOURCE_SHA
        and compact.get("pass") is False
        and compact.get("numeric_ok") is False
    ):
        raise ValueError("W7-S1 W5 compact authority is not closed")
    samples = compact.get("screen", {}).get("samples")
    if not isinstance(samples, Mapping) or "200" not in samples:
        raise ValueError("W7-S1 W5 iter200 authority is missing")
    initial_solution = None
    frozen_rhs = None
    frozen_outer_action = None
    frozen_residual = None
    sample_artifacts: dict[str, Any] = {}
    iteration = 200
    sample = samples[str(iteration)]
    artifacts = sample.get("artifacts") if isinstance(sample, Mapping) else None
    if not isinstance(artifacts, Mapping) or set(artifacts) != {
        "solution", "outer_action", "residual", "rhs"
    }:
        raise ValueError("W7-S1 W5 iter200 artifacts are incomplete")
    sample_artifacts[str(iteration)] = {}
    arrays: dict[str, np.ndarray] = {}
    try:
        for name in ("solution", "outer_action", "residual", "rhs"):
            record = artifacts[name]
            file_name = f"m6b_iter{iteration}_{name}.npy"
            if not isinstance(record, Mapping) or record.get("path") != file_name:
                raise ValueError(f"W7-S1 W5 artifact path is invalid: {file_name}")
            actual = _artifact(w5_raw_dir, file_name)
            if not (
                actual.get("present") is True
                and actual.get("sha256") == record.get("sha256")
                and actual.get("bytes") == record.get("bytes")
            ):
                raise ValueError(f"W7-S1 W5 file artifact differs: {file_name}")
            values = np.load(
                w5_raw_dir / file_name, allow_pickle=False, mmap_mode="r"
            )
            if not (
                values.dtype == np.dtype(np.complex128)
                and values.shape == (M6B_GLOBAL_ROWS,)
                and np.all(np.isfinite(values))
                and _m6b_w6a_w5_legacy_raw_array_sha256(values)
                == record.get("array_sha256")
            ):
                raise ValueError(f"W7-S1 W5 array artifact differs: {file_name}")
            arrays[name] = values
            sample_artifacts[str(iteration)][name] = {
                "path": file_name,
                "file_sha256": actual["sha256"],
                "array_sha256": record["array_sha256"],
                "bytes": actual["bytes"],
            }
        expected_residual = arrays["rhs"] - arrays["outer_action"]
        closure = float(
            np.linalg.norm(expected_residual - arrays["residual"])
            / max(np.linalg.norm(arrays["rhs"]), np.finfo(float).tiny)
        )
        rho = float(
            np.linalg.norm(arrays["residual"])
            / max(np.linalg.norm(arrays["rhs"]), np.finfo(float).tiny)
        )
        if (
            closure > 1.0e-12
            or not _finite_number(sample.get("true_relative_residual"))
            or abs(rho - float(sample["true_relative_residual"])) > 1.0e-12
            or abs(rho - M6B_W7_S1_INITIAL_RHO) > 1.0e-12
        ):
            raise ValueError("W7-S1 frozen W5 iter200 residual authority differs")
        initial_solution = np.array(arrays["solution"], copy=True)
        frozen_rhs = np.array(arrays["rhs"], copy=True)
        frozen_outer_action = np.array(arrays["outer_action"], copy=True)
        frozen_residual = np.array(arrays["residual"], copy=True)
    finally:
        del arrays

    if (
        initial_solution is None
        or frozen_rhs is None
        or frozen_outer_action is None
        or frozen_residual is None
    ):
        raise ValueError("W7-S1 initial W5 arrays are missing")
    return {
        "compact": {
            "path": str(compact_path),
            "file_sha256": compact_artifact["sha256"],
            "producer_source_sha": M6B_W7_S1_W5_SOURCE_SHA,
        },
        "raw_dir": str(w5_raw_dir),
        "samples": sample_artifacts,
        "frozen_iteration": 200,
        "frozen_true_relative_residual": M6B_W7_S1_INITIAL_RHO,
        "initial_solution": initial_solution,
        "frozen_rhs": frozen_rhs,
        "frozen_outer_action": frozen_outer_action,
        "frozen_residual": frozen_residual,
    }


def _m6b_w6a_predicted_live_set(
    *,
    old_retained_bytes: int,
    new_retained_bytes: int,
    old_work_bytes: int,
    new_work_bytes: int,
) -> dict[str, Any]:
    values = (old_retained_bytes, new_retained_bytes, old_work_bytes, new_work_bytes)
    if any(type(value) is not int or value < 0 for value in values):
        raise ValueError("W6A retained/work bytes must be nonnegative integers")
    retained_delta = new_retained_bytes - old_retained_bytes
    work_delta = new_work_bytes - old_work_bytes
    if retained_delta < 0 or work_delta < 0:
        raise ValueError("W6A new-minus-old deltas must be nonnegative")
    total = int(M6B_W5_EXPECTED_PROCESS_PEAK_BYTES + retained_delta + work_delta)
    return {
        "base_measured_w5_peak_bytes": M6B_W5_EXPECTED_PROCESS_PEAK_BYTES,
        "old_retained_bytes": old_retained_bytes,
        "new_retained_bytes": new_retained_bytes,
        "old_work_bytes": old_work_bytes,
        "new_work_bytes": new_work_bytes,
        "new_minus_old_retained_bytes": retained_delta,
        "new_minus_old_work_bytes": work_delta,
        "predicted_live_set_bytes": total,
        "limit_bytes": M6B_W6A_PREDICTED_LIVE_SET_LIMIT_BYTES,
        "gate": total <= M6B_W6A_PREDICTED_LIVE_SET_LIMIT_BYTES,
        "derived_not_measured": True,
        "is_measurement": False,
        "prediction_scope": "production_w6a_carrier_not_formal_measurement",
    }


def _m6b_w6a_scope(*, prediction: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(prediction, Mapping):
        raise ValueError("W6A prediction is missing")
    return {
        "schema": M6B_W6A_SCHEMA,
        "phase": M6B_W6A_PHASE,
        "degree": M6B_DEGREE,
        "h_nm": M6B_H_NM,
        "global_cells": M6B_GLOBAL_CELLS,
        "global_rows": M6B_GLOBAL_ROWS,
        "factor_count": M6B_FACTOR_COUNT,
        "factor_reuse_count": M6B_FACTOR_REUSE,
        "beta": 1.0,
        "fine_space": "uncondensed_fullspace",
        "operator": "A=Kcurl-k0^2*M_epsilon+A_DtN",
        "global_matrix": False,
        "augmented_matrix": False,
        "static_condensation": False,
        "trace_slab_pc": False,
        "schur": False,
        "explicit_C_materialized_count": 0,
        "explicit_D_materialized_count": 0,
        "dtn_matrix_free": True,
        "mpi_size": 1,
        "columns": M6B_W6A_COLUMNS,
        "legacy_columns": M6B_W6A_LEGACY_COLUMNS,
        "added_columns": M6B_W6A_ADDED_COLUMNS,
        "diffraction_orders": list(M6B_W6A_ORDERS),
        "z_planes": M6B_W6A_Z_PLANES,
        "components": M6B_W6A_COMPONENTS,
        "column_order": "legacy75_then_m_ascending_z_ascending_component_0_1_2",
        "phase_formula": "exp(i*((kx+2*pi*m/period_x)*x+ky*y))",
        "fixed_order": True,
        "scan": False,
        "az_builder_only": True,
        "az_production_retained": False,
        "dense_z_retained": False,
        "dense_az_retained": False,
        "predicted_live_set": dict(prediction),
        "formal_pass": False,
        "pde_pass": False,
    }


def _m6b_w6a_progress_emit(
    path: Path, event: str, *, elapsed_wall_seconds: float, **fields: Any
) -> None:
    if not _finite_number(elapsed_wall_seconds):
        raise ValueError("W6A progress elapsed time is invalid")
    record = {
        "schema": f"{M6B_W6A_SCHEMA}.progress.v1",
        "phase": M6B_W6A_PHASE,
        "event": event,
        "elapsed_wall_seconds": float(elapsed_wall_seconds),
        **fields,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(_canonical_json(record).decode("utf-8") + "\n")
        stream.flush()


def _m6b_w6a_progress_valid(path: Path) -> dict[str, Any]:
    try:
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return {"pass": False, "problems": [f"progress_read:{type(exc).__name__}"]}
    expected_events: list[str] = list(M6B_W6A_EVENTS)
    expected_events.extend("column_progress" for _ in range(M6B_W6A_COLUMNS))
    expected_events.extend("repeat_ready" for _ in M6B_W6A_REPEAT_COLUMNS)
    expected_events.extend(M6B_W6A_TRAILING_EVENTS)
    problems: list[str] = []
    if len(records) != len(expected_events):
        problems.append("progress_event_count")
    for index, event in enumerate(expected_events):
        record = records[index] if index < len(records) else None
        if not isinstance(record, Mapping) or record.get("event") != event:
            problems.append(f"progress_event_{index}")
            continue
        if record.get("schema") != f"{M6B_W6A_SCHEMA}.progress.v1" or record.get("phase") != M6B_W6A_PHASE:
            problems.append(f"progress_identity_{index}")
        if not _finite_number(record.get("elapsed_wall_seconds")):
            problems.append(f"progress_elapsed_{index}")
        if event == "column_progress":
            completed = index - len(M6B_W6A_EVENTS) + 1
            if record.get("completed_columns") != completed or record.get("total_columns") != M6B_W6A_COLUMNS:
                problems.append(f"progress_column_{completed}")
        elif event == "repeat_ready":
            repeat_index = index - len(M6B_W6A_EVENTS) - M6B_W6A_COLUMNS
            if (
                record.get("column_index") != M6B_W6A_REPEAT_COLUMNS[repeat_index]
                or record.get("completed_repeats") != repeat_index + 1
                or record.get("total_repeats") != len(M6B_W6A_REPEAT_COLUMNS)
            ):
                problems.append(f"progress_repeat_{repeat_index}")
    return {
        "pass": not problems,
        "problems": problems,
        "record_count": len(records),
        "events": [record.get("event") if isinstance(record, Mapping) else None for record in records],
    }


def _m6b_w6a_numeric_gate(residuals: Any) -> dict[str, Any]:
    required = {"20", "100", "150", "200"}
    checks = {
        f"rho390_le_rho75_{iteration}": False for iteration in sorted(required, key=int)
    }
    checks.update({"rho390_iter200": False, "improvement_vs_rho75": False})
    observed: dict[str, dict[str, float]] = {}
    problems: list[str] = []
    if not isinstance(residuals, Mapping) or set(residuals) != required:
        problems.append("residual_checkpoint_set")
    else:
        for iteration in sorted(required, key=int):
            item = residuals[iteration]
            if not isinstance(item, Mapping) or set(item) != {"rho75", "rho390"}:
                problems.append(f"residual_{iteration}_shape")
                continue
            rho75 = item["rho75"]
            rho390 = item["rho390"]
            if not (_finite_number(rho75) and _finite_number(rho390)) or rho75 < 0.0 or rho390 < 0.0:
                problems.append(f"residual_{iteration}_finite")
                continue
            observed[iteration] = {"rho75": float(rho75), "rho390": float(rho390)}
            checks[f"rho390_le_rho75_{iteration}"] = rho390 <= rho75 + 1.0e-12
    if "200" in observed:
        checks["rho390_iter200"] = observed["200"]["rho390"] <= M6B_W6A_RHO_LIMIT
        rho75 = observed["200"]["rho75"]
        if rho75 > 0.0:
            checks["improvement_vs_rho75"] = (
                1.0 - observed["200"]["rho390"] / rho75
            ) >= M6B_W6A_IMPROVEMENT_LIMIT
        else:
            problems.append("rho75_iter200_zero")
    problems.extend(key for key, passed in checks.items() if not passed)
    return {
        "checks": checks,
        "observed": observed,
        "problems": sorted(set(problems)),
        "pass": not problems and all(checks.values()),
    }


def _m6b_w6a_cache_record(h2b: Any, path: Path) -> dict[str, Any]:
    entries = [
        {
            "path": item["path"],
            "bytes": int(item["bytes"]),
            "sha256": item["sha256"],
        }
        for item in h2b._cache_snapshot(path)
    ]
    return {
        "entries": entries,
        "inventory_sha256": hashlib.sha256(
            h2b._canonical_json({"entries": entries})
        ).hexdigest(),
    }


def _m6b_w6a_jit_cache_valid(
    value: Any,
    h2b: Any,
    source_path: Path,
    target_path: Path,
) -> bool:
    try:
        source_now = _m6b_w6a_cache_record(h2b, source_path)
        target_now = _m6b_w6a_cache_record(h2b, target_path)
        return bool(
            isinstance(value, Mapping)
            and value.get("source_before") == value.get("source_after_forward")
            == value.get("source_after_surface") == value.get("source_final") == source_now
            and value.get("target_before") == value.get("target_after_forward")
            == value.get("target_after_surface") == value.get("target_final") == target_now
            and value.get("source") == str(source_path)
            and value.get("target") == str(target_path.resolve())
            and value.get("source_unchanged") is True
            and value.get("target_frozen_unchanged") is True
            and target_now == source_now
            and source_now.get("inventory_sha256") == M6B_W6A_JIT_INVENTORY_SHA256
        )
    except (OSError, TypeError, ValueError, KeyError):
        return False


def _m6b_w6a_source_valid(value: Any) -> bool:
    required = {
        "source_commit_full_sha",
        "tracked_source_dirty",
        "source_worktree_dirty",
        "nonignored_untracked_paths",
        "worktree_status_porcelain",
        "git_error",
    }
    return bool(
        isinstance(value, Mapping)
        and required <= set(value)
        and isinstance(value["source_commit_full_sha"], str)
        and len(value["source_commit_full_sha"]) == 40
        and all(char in "0123456789abcdef" for char in value["source_commit_full_sha"])
        and value["tracked_source_dirty"] is False
        and value["source_worktree_dirty"] is False
        and value["nonignored_untracked_paths"] == []
        and value["worktree_status_porcelain"] == []
        and value["git_error"] is None
    )


def _m6b_w6a_w5_compact_authority() -> dict[str, Any]:
    path = (ROOT / M6B_W6A_W5_COMPACT_RELATIVE_PATH).resolve()
    artifact = _artifact(ROOT, M6B_W6A_W5_COMPACT_RELATIVE_PATH)
    if (
        artifact.get("present") is not True
        or artifact.get("sha256") != M6B_W6A_W5_COMPACT_FILE_SHA256
    ):
        raise ValueError("W6A W5 compact authority file differs")
    record = _read_json(path)
    authority = record.get("authority")
    compiler = authority.get("factor_compiler") if isinstance(authority, Mapping) else None
    if not (
        _evidence_valid(record)
        and record.get("classification") == "NUMERIC_FAIL"
        and record.get("producer_source_sha") == M6B_W6A_W5_SOURCE_SHA
        and isinstance(compiler, Mapping)
    ):
        raise ValueError("W6A W5 compact authority is not closed")
    return {
        "path": str(path),
        "file_sha256": artifact["sha256"],
        "record": record,
        "factor_compiler": dict(compiler),
    }


def _m6b_w6a_legacy_columns(legacy: Mapping[str, Any]) -> tuple[Any, ...]:
    import numpy as np
    from src.solvers.hcurl_m6b_w6a_multi_order_range import W6ASparseColumn

    data = np.asarray(legacy["z_data"])
    indices = np.asarray(legacy["z_indices"])
    indptr = np.asarray(legacy["z_indptr"])
    result = []
    for column in range(M6B_W6A_LEGACY_COLUMNS):
        first, last = int(indptr[column]), int(indptr[column + 1])
        result.append(
            W6ASparseColumn(
                np.asarray(indices[first:last], dtype=np.int32),
                np.asarray(data[first:last], dtype=np.complex128),
            )
        )
    return tuple(result)


def _m6b_w6a_copy_residuals(
    source_dir: Path, raw_dir: Path
) -> dict[str, dict[str, Any]]:
    import shutil
    import numpy as np

    artifacts: dict[str, dict[str, Any]] = {}
    for iteration in M6B_W6A_W5_RESIDUAL_ITERATIONS:
        source_name = f"m6b_iter{iteration}_residual.npy"
        target_name = f"m6b_w6a_residual_iter{iteration}.npy"
        source = source_dir / source_name
        target = raw_dir / target_name
        if not source.is_file() or target.exists():
            raise FileNotFoundError(f"W6A frozen residual is unavailable: {source}")
        array = np.load(source, allow_pickle=False, mmap_mode="r")
        if (
            array.dtype != np.dtype(np.complex128)
            or list(array.shape) != [M6B_GLOBAL_ROWS]
            or not np.all(np.isfinite(array))
        ):
            raise ValueError(f"W6A frozen residual {source_name} is invalid")
        source_array_sha256 = _m6b_w2_array_sha256(array)
        shutil.copyfile(source, target)
        copied = np.load(target, allow_pickle=False, mmap_mode="r")
        if _m6b_w2_array_sha256(copied) != source_array_sha256:
            raise ValueError(f"W6A residual copy differs: {target_name}")
        artifacts[str(iteration)] = {
            "source": _artifact(source_dir, source_name),
            "copy": _artifact(raw_dir, target_name),
            "source_array_sha256": source_array_sha256,
            "copy_array_sha256": _m6b_w2_array_sha256(copied),
            "path": target_name,
            "present": True,
        }
    return artifacts


def _run_m6b_w6a_builder(
    run_dir: Path,
    legacy_store_dir: Path,
    w5_raw_dir: Path,
    jit_cache_source: Path,
    expected_source_sha: str,
) -> int:
    """Produce the real p6/h10 W6A carrier; this entry is never ordinary-default."""

    import gc
    import shutil
    import time

    import numpy as np
    from mpi4py import MPI

    h2b = __import__("benchmarks.run_task037_extra_h2b", fromlist=["*"])
    m6a = __import__("benchmarks.run_task037_extra_m6", fromlist=["*"])
    from benchmarks.run_task037_extra_h2 import _jsonable
    from src.solvers.hcurl_fullspace_dtn import (
        build_fullspace_dtn_action,
        build_fullspace_dtn_carrier_from_surface,
    )
    from src.solvers.hcurl_h2b_m6b_shifted_patch_pc import (
        M6BNumpyOuterActionBridge,
        build_m6b_outer_mat,
        build_m6b_volume_form,
    )
    from src.solvers.hcurl_m6b_w6a_multi_order_range import (
        W6AMultiOrderRangeDiagnostic,
        build_w6a_added_columns_from_fe,
        load_w1a_legacy_basis,
    )
    from src.solvers.hcurl_rank_one_mpc_action import build_task037_extra_h1r2_mpc_action

    run_dir = Path(run_dir).resolve()
    legacy_store_dir = Path(legacy_store_dir).resolve()
    w5_raw_dir = Path(w5_raw_dir).resolve()
    jit_cache_source = Path(jit_cache_source).resolve()
    if run_dir.exists():
        raise FileExistsError(f"W6A builder refuses existing directory: {run_dir}")
    if not legacy_store_dir.is_dir() or not w5_raw_dir.is_dir():
        raise FileNotFoundError("W6A frozen W1A/W5 authority is missing")
    if not jit_cache_source.is_dir():
        raise FileNotFoundError("W6A JIT source is missing")
    if MPI.COMM_WORLD.size != 1:
        raise RuntimeError("W6A builder is fixed to MPI1")

    w5_authority = _m6b_w6a_w5_compact_authority()
    frozen_compiler = w5_authority["factor_compiler"]
    h2a = h2b._lazy_h2a()
    runtime_identity = _m6b_runtime_identity(
        h2b,
        h2a,
        MPI.COMM_WORLD,
        compiler_probe=False,
        compiler=frozen_compiler,
    )
    if not _m6b_w6a_runtime_valid(
        runtime_identity, frozen_compiler=frozen_compiler
    ):
        raise RuntimeError("W6A qualified runtime identity is not closed")
    source_start = h2b._light_source()
    if (
        source_start.get("source_commit_full_sha") != expected_source_sha
        or not _m6b_w6a_source_valid(source_start)
    ):
        raise RuntimeError("W6A builder source identity is not clean or expected")

    run_dir.mkdir(parents=True)
    cache_dir = run_dir / "jit_cache"
    shutil.copytree(jit_cache_source, cache_dir)
    progress_path = run_dir / "w6a_progress.jsonl"
    started = time.perf_counter()

    def emit(event: str, **fields: Any) -> None:
        _m6b_w6a_progress_emit(
            progress_path,
            event,
            elapsed_wall_seconds=float(time.perf_counter() - started),
            **fields,
        )
        print(json.dumps({"event": event, **fields}, sort_keys=True), flush=True)

    emit("authority_validated", source_sha=expected_source_sha)
    source_cache_before = _m6b_w6a_cache_record(h2b, jit_cache_source)
    target_cache_before = _m6b_w6a_cache_record(h2b, cache_dir)
    if source_cache_before["inventory_sha256"] != M6B_W6A_JIT_INVENTORY_SHA256:
        raise ValueError("W6A JIT source inventory authority differs")
    if target_cache_before != source_cache_before:
        raise ValueError("W6A copied JIT cache differs from source")
    cfg = mesh_data = function_space = floquet = None
    physical_action = dtn_action = outer_mat = outer_context = None
    bridge = template = None
    surface_assemblers = None
    volume_ufl = epsilon = abs_epsilon = beta = None
    diagnostic = None
    try:
        cfg, mesh_data, function_space, floquet, modes = m6a._production_objects(
            run_dir, mesh_name="m6b_w6a_mesh"
        )
        identity = m6a._p6_identity(mesh_data, function_space, floquet)
        if identity != {
            "global_cells": M6B_GLOBAL_CELLS,
            "local_cells": M6B_GLOBAL_CELLS,
            "local_nloc": M6B_LOCAL_NLOC,
            "global_rows": M6B_GLOBAL_ROWS,
            "constraint_count": M6B_CONSTRAINTS,
        }:
            raise ValueError(f"W6A p6/h10 identity differs: {identity}")
        emit("mesh_ready", global_cells=identity["global_cells"])
        emit("space_ready", global_rows=identity["global_rows"])
        emit("floquet_mpc_ready", constraint_count=identity["constraint_count"])
        emit("cache_ready", inventory_sha256=target_cache_before["inventory_sha256"])
        physical_ufl, epsilon, abs_epsilon, beta, tag_coverage = build_m6b_volume_form(
            function_space, mesh_data, cfg, beta=0.0
        )
        volume_ufl = physical_ufl
        physical_action = build_task037_extra_h1r2_mpc_action(
            physical_ufl,
            floquet.mpc,
            task037_extra_h1r2=True,
            jit_options=h2b._expected_jit_options(cache_dir),
        )
        target_after_forward = _m6b_w6a_cache_record(h2b, cache_dir)
        source_after_forward = _m6b_w6a_cache_record(h2b, jit_cache_source)
        if target_after_forward != target_cache_before or source_after_forward != source_cache_before:
            raise ValueError("W6A forward form changed the frozen JIT cache")
        surface_assemblers = m6a._surface_assemblers(
            function_space, mesh_data, cfg, modes, cache_dir
        )
        target_after_surface = _m6b_w6a_cache_record(h2b, cache_dir)
        source_after_surface = _m6b_w6a_cache_record(h2b, jit_cache_source)
        if target_after_surface != target_after_forward or source_after_surface != source_cache_before:
            raise ValueError("W6A surface construction changed the frozen JIT cache")
        dtn_carrier = build_fullspace_dtn_carrier_from_surface(
            modes, surface_assemblers, floquet.mpc, cfg, expected_mode_count=80
        )
        dtn_action = build_fullspace_dtn_action(dtn_carrier, comm=MPI.COMM_WORLD)
        outer_mat, outer_context = build_m6b_outer_mat(
            physical_action,
            dtn_action,
            owned_rows=M6B_GLOBAL_ROWS,
            global_rows=M6B_GLOBAL_ROWS,
            comm=MPI.COMM_WORLD,
        )
        template = outer_mat.createVecRight()
        ownership = tuple(int(value) for value in template.getOwnershipRange())
        bridge = M6BNumpyOuterActionBridge(outer_context, template)
        emit("outer_ready", tag_coverage=tag_coverage)
        legacy = load_w1a_legacy_basis(legacy_store_dir)
        legacy_columns = _m6b_w6a_legacy_columns(legacy)
        emit("legacy_basis_ready")
        old_audit = legacy["audit"]
        old_retained = int(old_audit["retained_total_bytes"])
        old_work = int(old_audit["bounded_work_bytes"])
        added_columns, fe_audit = build_w6a_added_columns_from_fe(
            function_space,
            mesh_data,
            floquet,
            template,
            cfg,
            ownership_range=ownership,
        )
        columns = legacy_columns + added_columns
        new_nnz = sum(int(column.indices.size) for column in columns)
        new_z_bytes = int(new_nnz * (16 + 4) + (M6B_W6A_COLUMNS + 1) * 4)
        new_r_bytes = int(M6B_W6A_COLUMNS * M6B_W6A_COLUMNS * 16)
        retained_sparse = new_z_bytes + new_r_bytes
        if retained_sparse > int(0.20 * 1024**3):
            raise ValueError("W6A retained sparse Z+R exceeds the fixed 0.20 GiB gate")
        new_retained = retained_sparse + M6B_W6A_MANIFEST_RESERVE_BYTES
        new_work = int(5 * M6B_GLOBAL_ROWS * 16)
        prediction = _m6b_w6a_predicted_live_set(
            old_retained_bytes=old_retained,
            new_retained_bytes=new_retained,
            old_work_bytes=old_work,
            new_work_bytes=new_work,
        )
        if prediction["gate"] is not True:
            raise ValueError("W6A predicted live set exceeds the fixed limit")

        residual_artifacts = _m6b_w6a_copy_residuals(w5_raw_dir, run_dir)

        def action(values: np.ndarray) -> np.ndarray:
            return bridge.apply(values)

        def progress(event: str, first: int, second: int) -> None:
            if event == "column_progress":
                emit("column_progress", completed_columns=first, total_columns=second)
            elif event == "repeat_ready":
                emit(
                    "repeat_ready",
                    column_index=first,
                    completed_repeats=second,
                    total_repeats=len(M6B_W6A_REPEAT_COLUMNS),
                )
            elif event == "az_ready":
                emit("az_ready", completed=first, total=second)
            elif event == "gram_ready":
                emit("gram_ready", completed=first, total=second)
            else:
                raise ValueError(f"W6A progress event is unknown: {event}")

        diagnostic = W6AMultiOrderRangeDiagnostic.from_columns(
            columns,
            action,
            global_rows=M6B_GLOBAL_ROWS,
            ownership_range=ownership,
            scratch_dir=run_dir / "az_scratch",
            identity={
                "source_sha": expected_source_sha,
                "operator_identity": "A=Kcurl-k0^2*M_epsilon+A_DtN",
                "legacy_basis_manifest_sha256": legacy["basis_manifest_sha256"],
                "legacy_column_count": M6B_W6A_LEGACY_COLUMNS,
                "fine_space": "uncondensed_fullspace",
                "global_matrix": False,
                "static_condensation": False,
                "trace_slab_pc": False,
                "dtn_matrix_free": True,
                "physical_form_beta": 0.0,
                "coarse_shifted_beta": 1.0,
            },
            legacy_basis=legacy,
            progress=progress,
        )
        del columns, legacy_columns, added_columns, legacy
        gc.collect()
        diagnostic.save(run_dir / "sparse_range_store")
        observed: dict[str, dict[str, float]] = {}
        for iteration in M6B_W6A_W5_RESIDUAL_ITERATIONS:
            path = run_dir / f"m6b_w6a_residual_iter{iteration}.npy"
            values = np.load(path, allow_pickle=False, mmap_mode="r")
            result = diagnostic.compare_range_orders(values)
            observed[str(iteration)] = {
                "rho75": float(result["rho75"]),
                "rho390": float(result["rho390"]),
                "relative_improvement": float(result["relative_improvement"]),
            }
        emit("residuals_ready", checkpoints=list(observed))
        numeric = _m6b_w6a_numeric_gate(
            {key: {"rho75": value["rho75"], "rho390": value["rho390"]} for key, value in observed.items()}
        )
        target_final = _m6b_w6a_cache_record(h2b, cache_dir)
        source_final = _m6b_w6a_cache_record(h2b, jit_cache_source)
        source_end = h2b._light_source()
        emit("summary_ready")
        summary = {
            "schema": M6B_W6A_SCHEMA,
            "status": "builder_complete" if numeric["pass"] else "gate_failed",
            "formal_pass": False,
            "pde_pass": False,
            "qualification": "pre_formal_measurement",
            "w5_compact_authority": {
                "path": w5_authority["path"],
                "file_sha256": w5_authority["file_sha256"],
                "producer_source_sha": w5_authority["record"]["producer_source_sha"],
            },
            "runtime_identity": runtime_identity,
            "source_at_start": source_start,
            "source_at_end": source_end,
            "scope": _m6b_w6a_scope(prediction=prediction),
            "prediction": prediction,
            "p6_identity": identity,
            "z_planes": fe_audit,
            "legacy_z_identity": diagnostic.legacy_z_identity,
            "store_manifest_artifact": _artifact(run_dir, "sparse_range_store/manifest.json"),
            "carrier_audit": diagnostic.audit,
            "residual_artifacts": residual_artifacts,
            "residual_results": observed,
            "numeric_gate": numeric,
            "action_audit": {
                "base": diagnostic.action_counts["base"],
                "selected_repeat": diagnostic.action_counts["selected_repeat"],
                "total": diagnostic.action_counts["total"],
                "outer_forward_apply_count": bridge.audit["forward_apply_count"],
                "bridge": bridge.audit,
                "outer_context": _jsonable(dict(outer_context.audit)),
                "physical_action": _jsonable(dict(physical_action.audit)),
                "dtn_action": _jsonable(dict(dtn_action.audit)),
            },
            "jit_cache": {
                "source": str(jit_cache_source),
                "target": str(cache_dir),
                "source_before": source_cache_before,
                "source_after_forward": source_after_forward,
                "source_after_surface": source_after_surface,
                "source_final": source_final,
                "target_before": target_cache_before,
                "target_after_forward": target_after_forward,
                "target_after_surface": target_after_surface,
                "target_final": target_final,
                "source_unchanged": source_final == source_cache_before,
                "target_frozen_unchanged": target_final == target_after_surface,
            },
            "architecture": {
                "fine_space": "uncondensed_fullspace",
                "global_matrix": False,
                "static_condensation": False,
                "trace_slab_pc": False,
                "schur": False,
                "explicit_C_materialized_count": 0,
                "explicit_D_materialized_count": 0,
                "dtn_matrix_free": True,
                "dense_z_retained": False,
                "dense_az_retained": False,
                "az_production_retained": False,
            },
            "progress_artifact": _artifact(run_dir, "w6a_progress.jsonl"),
            "progress": _m6b_w6a_progress_valid(progress_path),
            "builder_limits": {
                "timeout_seconds": M6B_W6A_BUILDER_TIMEOUT_SECONDS,
                "completed_peak_rss_bytes": M6B_W6A_BUILDER_RSS_LIMIT_BYTES,
                "watchdog_rss_bytes": M6B_W6A_WATCHDOG_RSS_LIMIT_BYTES,
                "swap_bytes": M6B_SWAP_LIMIT_BYTES,
                "formal_peak_gate": "not_measured",
            },
            "elapsed_wall_seconds": float(time.perf_counter() - started),
        }
        _write_json(run_dir / "w6a_summary.json", _attach_evidence(summary))
        return 0
    finally:
        if diagnostic is not None:
            diagnostic.close()
        if bridge is not None:
            bridge.destroy()
        if template is not None:
            template.destroy()
        if outer_mat is not None:
            outer_mat.destroy()
        if outer_context is not None:
            outer_context.destroy()
        if dtn_action is not None:
            dtn_action.destroy()
        if physical_action is not None:
            physical_action.destroy()
        if surface_assemblers is not None:
            for assembler in surface_assemblers.values():
                destroy = getattr(assembler, "destroy", None)
                if destroy is not None:
                    destroy()
        del volume_ufl, epsilon, abs_epsilon, beta
        gc.collect()


def _m6b_w6a_timeline_valid(path: Path) -> dict[str, Any]:
    try:
        records = [
            json.loads(line)
            for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if not records:
            raise ValueError("W6A watchdog timeline is empty")
        peak = max(int(record["rss_bytes"]) for record in records)
        swap = max(int(record["swap_bytes"]) for record in records)
        compiler = sorted(
            {
                int(pid)
                for record in records
                for pid in record.get("compiler_descendant_pids", [])
            }
        )
        return {
            "pass": all(
                type(record) is dict
                and record.get("phase") == M6B_W6A_PHASE
                and type(record.get("rss_bytes")) is int
                and type(record.get("swap_bytes")) is int
                for record in records
            )
            and swap == 0
            and compiler == [],
            "records": len(records),
            "peak_rss_bytes": peak,
            "swap_bytes": swap,
            "compiler_descendant_pids": compiler,
        }
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        return {
            "pass": False,
            "records": 0,
            "peak_rss_bytes": None,
            "swap_bytes": None,
            "compiler_descendant_pids": None,
            "problems": [f"timeline:{type(exc).__name__}"],
        }


def _m6b_w6a_artifact_inventory_valid(
    inventory: Any, raw_dir: Path, watchdog_dir: Path
) -> bool:
    if not isinstance(inventory, Mapping):
        return False
    raw = inventory.get("raw")
    watchdog = inventory.get("watchdog")
    if not isinstance(raw, list) or not isinstance(watchdog, list):
        return False
    expected_raw = {
        "w6a_summary.json",
        "w6a_progress.jsonl",
        "sparse_range_store/manifest.json",
        "sparse_range_store/z_data.npy",
        "sparse_range_store/z_indices.npy",
        "sparse_range_store/z_indptr.npy",
        "sparse_range_store/gram.npy",
        "sparse_range_store/r_factor.npy",
        *(f"m6b_w6a_residual_iter{iteration}.npy" for iteration in M6B_W6A_W5_RESIDUAL_ITERATIONS),
    }
    expected_watchdog = {
        f"{M6B_W6A_PHASE}_timeline.jsonl",
        f"{M6B_W6A_PHASE}_stdout.txt",
        f"{M6B_W6A_PHASE}_root_pid.json",
    }
    if {item.get("path") for item in raw if isinstance(item, Mapping)} != expected_raw:
        return False
    if {item.get("path") for item in watchdog if isinstance(item, Mapping)} != expected_watchdog:
        return False
    for record, root in [
        *( (item, raw_dir) for item in raw),
        *((item, watchdog_dir) for item in watchdog),
    ]:
        if (
            not isinstance(record, Mapping)
            or record.get("present") is not True
            or not isinstance(record.get("path"), str)
            or type(record.get("bytes")) is not int
            or record.get("bytes", 0) <= 0
            or not _m6b_w6a_valid_sha(record.get("sha256"))
        ):
            return False
        path = (root / record["path"]).resolve()
        if (
            not path.is_file()
            or path.stat().st_size != record["bytes"]
            or _sha256_file(path) != record["sha256"]
        ):
            return False
    return True


def _m6b_w6a_valid_sha(value: Any) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def _m6b_w6a_fe_audit_valid(value: Any) -> bool:
    try:
        import numpy as np
        from src.common.config_3d import target_stage4_config
        from src.solvers.hcurl_m6b_w6a_multi_order_range import _array_sha256

        if not isinstance(value, Mapping) or value.get("column_count") != M6B_W6A_ADDED_COLUMNS:
            return False
        planes = np.asarray(value.get("z_planes"), dtype=np.float64)
        target_cfg = target_stage4_config(degree=6, h_nm=10.0)
        expected_planes = np.linspace(
            float(target_cfg.domain_z_min),
            float(target_cfg.domain_z_max),
            M6B_W6A_Z_PLANES,
            dtype=np.float64,
        )
        if (
            planes.shape != (M6B_W6A_Z_PLANES,)
            or not np.all(np.isfinite(planes))
            or not np.all(np.diff(planes) > 0.0)
            or not np.isfinite(float(value.get("domain_z_min")))
            or not np.isfinite(float(value.get("domain_z_max")))
            or float(value["domain_z_min"]) != float(target_cfg.domain_z_min)
            or float(value["domain_z_max"]) != float(target_cfg.domain_z_max)
            or not np.array_equal(planes, expected_planes)
            or value.get("z_planes_array_sha256") != _array_sha256(planes)
            or value.get("dense_candidates_retained") is not False
            or value.get("fixed_order") is not True
        ):
            return False
        columns = value.get("column_audit")
        if not isinstance(columns, list) or len(columns) != M6B_W6A_ADDED_COLUMNS:
            return False
        for offset, record in enumerate(columns):
            if (
                not isinstance(record, Mapping)
                or record.get("column_index") != M6B_W6A_LEGACY_COLUMNS + offset
                or type(record.get("nnz")) is not int
                or record["nnz"] <= 0
                or not _finite_number(record.get("norm"))
                or abs(float(record["norm"]) - 1.0) > 1.0e-12
                or not _m6b_w6a_valid_sha(record.get("indices_array_sha256"))
                or not _m6b_w6a_valid_sha(record.get("values_array_sha256"))
            ):
                return False
        return True
    except (ImportError, IndexError, KeyError, TypeError, ValueError):
        return False


def _m6b_w8a_fe_audit_valid(value: Any) -> bool:
    try:
        import numpy as np
        from src.common.config_3d import target_stage4_config
        from src.solvers.hcurl_m6b_w6a_multi_order_range import _array_sha256
        from src.solvers.hcurl_m6b_w8a_z_bubble_range import fixed_w8a_column_specs

        if not isinstance(value, Mapping) or value.get("column_count") != M6B_W8A_ADDED_COLUMNS:
            return False
        planes = np.asarray(value.get("z_planes"), dtype=np.float64)
        target_cfg = target_stage4_config(degree=6, h_nm=10.0)
        expected_planes = np.linspace(
            float(target_cfg.domain_z_min),
            float(target_cfg.domain_z_max),
            M6B_W8A_INTERVALS + 1,
            dtype=np.float64,
        )
        if (
            planes.shape != (M6B_W8A_INTERVALS + 1,)
            or not np.all(np.isfinite(planes))
            or not np.all(np.diff(planes) > 0.0)
            or value.get("domain_z_min") != float(target_cfg.domain_z_min)
            or value.get("domain_z_max") != float(target_cfg.domain_z_max)
            or not np.array_equal(planes, expected_planes)
            or value.get("z_planes_array_sha256") != _array_sha256(planes)
            or value.get("dense_candidates_retained") is not False
            or value.get("fixed_order") is not True
            or value.get("component") != M6B_W8A_COMPONENT
            or value.get("diffraction_orders") != list(M6B_W8A_ORDERS)
            or value.get("bubble_degrees") != list(M6B_W8A_BUBBLE_DEGREES)
        ):
            return False
        records = value.get("column_audit")
        expected = fixed_w8a_column_specs()[M6B_W8A_LEGACY_COLUMNS:]
        if not isinstance(records, list) or len(records) != len(expected):
            return False
        for spec, record in zip(expected, records):
            if (
                not isinstance(record, Mapping)
                or record.get("column_index") != spec.column_index
                or record.get("order_m") != spec.order_m
                or record.get("interval") != spec.interval
                or record.get("bubble_degree") != spec.bubble_degree
                or record.get("component") != spec.component
                or type(record.get("nnz")) is not int
                or record["nnz"] <= 0
                or not _finite_number(record.get("norm"))
                or abs(float(record["norm"]) - 1.0) > 1.0e-12
                or not _m6b_w6a_valid_sha(record.get("indices_array_sha256"))
                or not _m6b_w6a_valid_sha(record.get("values_array_sha256"))
            ):
                return False
        return True
    except (ImportError, IndexError, KeyError, TypeError, ValueError):
        return False


def _m6b_w6a_action_audit_valid(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    bridge = value.get("bridge")
    outer = value.get("outer_context")
    physical = value.get("physical_action")
    dtn = value.get("dtn_action")
    outer_ok = bool(
        isinstance(outer, Mapping)
        and outer.get("apply_count") == M6B_W6A_COLUMNS + len(M6B_W6A_REPEAT_COLUMNS)
        and outer.get("matrix_type") == "python_action_only"
        and outer.get("global_matrix") is False
        and outer.get("augmented_matrix") is False
        and outer.get("static_condensation") is False
        and outer.get("trace_slab") is False
        and outer.get("explicit_C_materialized_count") == 0
        and outer.get("explicit_D_materialized_count") == 0
    )
    physical_ok = bool(
        isinstance(physical, Mapping)
        and physical.get("apply_count") == M6B_W6A_COLUMNS + len(M6B_W6A_REPEAT_COLUMNS)
        and physical.get("global_matrix_materialized") is False
        and physical.get("global_constraint_matrix_materialized") is False
        and physical.get("global_condensed_schur_materialized") is False
        and physical.get("cell_schur_matrix_materialized") is False
        and physical.get("slab_matrix_materialized") is False
        and physical.get("retained_dense_cell_tensor_count") == 0
        and physical.get("dense_cell_tensor_materialized_per_apply") is False
        and physical.get("factor_count") == 0
        and physical.get("ksp_created") is False
        and physical.get("cell_schur_matrix_nnz") == 0
        and physical.get("slab_matrix_nnz") == 0
        and physical.get("explicit_C_materialized_count") == 0
        and physical.get("explicit_D_materialized_count") == 0
        and physical.get("ordinary_default_changed") is False
    )
    dtn_ok = bool(
        isinstance(dtn, Mapping)
        and dtn.get("apply_count") == M6B_W6A_COLUMNS + len(M6B_W6A_REPEAT_COLUMNS)
        and dtn.get("matrix_type") == "python_action_only"
        and dtn.get("fine_space") == "uncondensed_fullspace"
        and dtn.get("condensation") is False
        and dtn.get("static_condensed_operator_used") is False
        and dtn.get("trace_slab_pc_used") is False
        and dtn.get("global_matrix_materialized") is False
        and dtn.get("augmented_matrix_materialized") is False
        and dtn.get("explicit_C_materialized_count") == 0
        and dtn.get("explicit_D_materialized_count") == 0
        and dtn.get("fe_sized_allgather") is False
        and dtn.get("modal_allreduce_count_per_apply") == 1
        and dtn.get("modal_allreduce_count_per_hermitian_apply") == 1
    )
    return bool(
        value.get("base") == M6B_W6A_COLUMNS
        and value.get("selected_repeat") == len(M6B_W6A_REPEAT_COLUMNS)
        and value.get("total") == M6B_W6A_COLUMNS + len(M6B_W6A_REPEAT_COLUMNS)
        and value.get("outer_forward_apply_count") == M6B_W6A_COLUMNS + len(M6B_W6A_REPEAT_COLUMNS)
        and isinstance(bridge, Mapping)
        and bridge.get("vector_create_count") == 2
        and bridge.get("fixed_work_vectors") == 2
        and bridge.get("per_apply_vec_creation") == 0
        and bridge.get("forward_apply_count") == M6B_W6A_COLUMNS + len(M6B_W6A_REPEAT_COLUMNS)
        and outer_ok
        and physical_ok
        and dtn_ok
    )


def _m6b_w6a_watchdog_contract_valid(
    watchdog: Any,
    *,
    raw_dir: Path,
    legacy_store_dir: Path,
    w5_raw_dir: Path,
    jit_cache_source: Path,
    expected_source_sha: str,
) -> bool:
    if not isinstance(watchdog, Mapping) or not _evidence_valid(watchdog):
        return False
    source_start = watchdog.get("source_at_start")
    source_end = watchdog.get("source_at_end")
    command = watchdog.get("command")
    expected_command = [
        sys.executable,
        "-m",
        "benchmarks.run_task037_extra_m6b",
        "m6b-w6a-builder",
        "--run-dir",
        str(raw_dir),
        "--legacy-store-dir",
        str(legacy_store_dir),
        "--w5-raw-dir",
        str(w5_raw_dir),
        "--jit-cache-source",
        str(jit_cache_source),
        "--expected-source-sha",
        expected_source_sha,
    ]
    return bool(
        watchdog.get("schema") == M6B_W6A_WATCHDOG_SCHEMA
        and watchdog.get("phase") == M6B_W6A_PHASE
        and watchdog.get("status") == "measurement_complete"
        and watchdog.get("formal_pass") is False
        and watchdog.get("pde_pass") is False
        and _m6b_w6a_source_valid(source_start)
        and _m6b_w6a_source_valid(source_end)
        and source_start.get("source_commit_full_sha") == expected_source_sha
        and source_end.get("source_commit_full_sha") == expected_source_sha
        and command == expected_command
        and isinstance(watchdog.get("process"), Mapping)
        and watchdog["process"].get("return_code") == 0
        and watchdog["process"].get("termination") is None
        and isinstance(watchdog.get("drain"), Mapping)
        and watchdog["drain"].get("gone") is True
        and watchdog.get("source_end_clean") is True
        and watchdog.get("resource_limits") == {
            "timeout_seconds": M6B_W6A_BUILDER_TIMEOUT_SECONDS,
            "watchdog_rss_bytes": M6B_W6A_WATCHDOG_RSS_LIMIT_BYTES,
            "completion_peak_rss_bytes": M6B_W6A_BUILDER_RSS_LIMIT_BYTES,
            "swap_bytes": 0,
        }
    )


def _m6b_w6a_formal_gate(
    *,
    summary: Mapping[str, Any],
    watchdog: Mapping[str, Any],
    progress: Mapping[str, Any],
    timeline: Mapping[str, Any],
    store_validation: Mapping[str, Any],
    numeric: Mapping[str, Any],
    artifact_inventory_ok: bool,
    residual_files_ok: bool,
    watchdog_contract_ok: bool,
    expected_source_sha: str,
    runtime_identity_ok: bool,
    actual_prediction: Mapping[str, Any] | None = None,
    actual_store_audit: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    process = watchdog.get("process")
    drain = watchdog.get("drain")
    prediction = summary.get("prediction")
    prediction_ok = False
    if isinstance(prediction, Mapping):
        keys = (
            "old_retained_bytes",
            "new_retained_bytes",
            "old_work_bytes",
            "new_work_bytes",
        )
        if all(type(prediction.get(key)) is int for key in keys):
            try:
                prediction_ok = bool(
                    prediction == _m6b_w6a_predicted_live_set(
                        old_retained_bytes=prediction["old_retained_bytes"],
                        new_retained_bytes=prediction["new_retained_bytes"],
                        old_work_bytes=prediction["old_work_bytes"],
                        new_work_bytes=prediction["new_work_bytes"],
                    )
                    and prediction.get("gate") is True
                )
            except (TypeError, ValueError):
                prediction_ok = False
    carrier = summary.get("carrier_audit")
    architecture = summary.get("architecture")
    source_start = summary.get("source_at_start")
    source_end = summary.get("source_at_end")
    p6_identity = summary.get("p6_identity")
    action_audit = summary.get("action_audit")
    actual_prediction_ok = (
        True
        if actual_prediction is None
        else summary.get("prediction") == actual_prediction
    )
    actual_carrier_ok = True
    if actual_store_audit is not None:
        actual_carrier_ok = bool(
            isinstance(carrier, Mapping)
            and type(actual_store_audit.get("z_retained_bytes")) is int
            and type(actual_store_audit.get("r_retained_bytes")) is int
            and type(actual_store_audit.get("retained_z_r_bytes")) is int
            and type(actual_store_audit.get("bounded_work_bytes")) is int
            and actual_store_audit["retained_z_r_bytes"] <= int(0.20 * 1024**3)
            and carrier.get("z_retained_bytes") == actual_store_audit["z_retained_bytes"]
            and carrier.get("r_retained_bytes") == actual_store_audit["r_retained_bytes"]
            and carrier.get("retained_z_r_bytes") == actual_store_audit["retained_z_r_bytes"]
            and carrier.get("bounded_work_bytes") == actual_store_audit["bounded_work_bytes"]
            and isinstance(actual_store_audit.get("factor_audit"), Mapping)
            and isinstance(carrier.get("factor_audit"), Mapping)
            and carrier["factor_audit"].get("rank")
            == actual_store_audit["factor_audit"].get("rank")
            and carrier["factor_audit"].get("normal_closure")
            == actual_store_audit["factor_audit"].get("normal_closure")
        )
    checks = {
        "producer_evidence": _evidence_valid(summary),
        "runtime_identity": runtime_identity_ok is True,
        "producer_status": summary.get("status") == "builder_complete"
        and summary.get("formal_pass") is False
        and summary.get("pde_pass") is False,
        "source_clean": bool(
            _m6b_w6a_source_valid(source_start)
            and _m6b_w6a_source_valid(source_end)
            and source_start.get("source_commit_full_sha") == expected_source_sha
            and source_end.get("source_commit_full_sha") == expected_source_sha
        ),
        "progress": progress.get("pass") is True,
        "timeline": bool(
            timeline.get("pass") is True
            and timeline.get("records", 0) > 0
            and timeline.get("swap_bytes") == 0
            and timeline.get("compiler_descendant_pids") == []
            and isinstance(process, Mapping)
            and timeline.get("peak_rss_bytes") == process.get("peak_rss_bytes")
            and type(timeline.get("peak_rss_bytes")) is int
            and timeline["peak_rss_bytes"] < M6B_W6A_BUILDER_RSS_LIMIT_BYTES
        ),
        "process": bool(
            isinstance(process, Mapping)
            and process.get("return_code") == 0
            and process.get("termination") is None
            and type(process.get("peak_rss_bytes")) is int
            and process["peak_rss_bytes"] < M6B_W6A_BUILDER_RSS_LIMIT_BYTES
            and process.get("swap_bytes") == 0
            and isinstance(drain, Mapping)
            and drain.get("gone") is True
        ),
        "watchdog_limits": watchdog.get("resource_limits") == {
            "timeout_seconds": M6B_W6A_BUILDER_TIMEOUT_SECONDS,
            "watchdog_rss_bytes": M6B_W6A_WATCHDOG_RSS_LIMIT_BYTES,
            "completion_peak_rss_bytes": M6B_W6A_BUILDER_RSS_LIMIT_BYTES,
            "swap_bytes": 0,
        },
        "watchdog_contract": watchdog_contract_ok,
        "prediction": prediction_ok,
        "actual_payload_prediction": actual_prediction_ok,
        "actual_carrier_payload": actual_carrier_ok,
        "store": store_validation.get("pass") is True,
        "numeric": numeric.get("pass") is True,
        "residual_files": residual_files_ok,
        "artifact_inventory": artifact_inventory_ok,
        "p6_identity": p6_identity == {
            "global_cells": M6B_GLOBAL_CELLS,
            "local_cells": M6B_GLOBAL_CELLS,
            "local_nloc": M6B_LOCAL_NLOC,
            "global_rows": M6B_GLOBAL_ROWS,
            "constraint_count": M6B_CONSTRAINTS,
        },
        "scope": bool(
            isinstance(summary.get("scope"), Mapping)
            and isinstance(prediction, Mapping)
            and summary["scope"] == _m6b_w6a_scope(prediction=prediction)
        ),
        "action_audit": _m6b_w6a_action_audit_valid(action_audit),
        "fe_audit": _m6b_w6a_fe_audit_valid(summary.get("z_planes")),
        "architecture": bool(
            isinstance(architecture, Mapping)
            and architecture.get("fine_space") == "uncondensed_fullspace"
            and architecture.get("global_matrix") is False
            and architecture.get("static_condensation") is False
            and architecture.get("trace_slab_pc") is False
            and architecture.get("explicit_C_materialized_count") == 0
            and architecture.get("explicit_D_materialized_count") == 0
            and architecture.get("dtn_matrix_free") is True
            and architecture.get("dense_z_retained") is False
            and architecture.get("dense_az_retained") is False
            and architecture.get("az_production_retained") is False
        ),
        "carrier_audit": bool(
            isinstance(carrier, Mapping)
            and carrier.get("columns") == M6B_W6A_COLUMNS
            and carrier.get("action_counts") == {"base": 390, "selected_repeat": 4, "total": 394}
            and carrier.get("repeat_exact") is True
            and carrier.get("az_production_retained") is False
            and carrier.get("dense_z_retained") is False
            and carrier.get("dense_az_retained") is False
            and carrier.get("retained_z_r_gate") is True
            and isinstance(carrier.get("factor_audit"), Mapping)
            and carrier["factor_audit"].get("rank") == M6B_W6A_COLUMNS
            and _finite_number(carrier["factor_audit"].get("normal_closure"))
            and carrier["factor_audit"].get("normal_closure") <= M6B_W6A_NORMAL_CLOSURE_LIMIT
        ),
    }
    return {
        "checks": checks,
        "pass": all(checks.values()),
        "problems": sorted(name for name, passed in checks.items() if not passed),
    }


def _run_m6b_w6a_watchdog(
    run_dir: Path,
    watchdog_dir: Path,
    legacy_store_dir: Path,
    w5_raw_dir: Path,
    jit_cache_source: Path,
    expected_source_sha: str,
) -> int:
    """Run one W6A builder under the repository's existing process monitor."""

    import time

    h2b = __import__("benchmarks.run_task037_extra_h2b", fromlist=["*"])
    run_dir = Path(run_dir).resolve()
    watchdog_dir = Path(watchdog_dir).resolve()
    if run_dir.exists() or watchdog_dir.exists():
        raise FileExistsError("W6A watchdog refuses existing raw/watchdog paths")
    source_start = h2b._light_source()
    if (
        source_start.get("source_commit_full_sha") != expected_source_sha
        or not _m6b_w6a_source_valid(source_start)
    ):
        raise RuntimeError("W6A watchdog source identity is not clean or expected")
    watchdog_dir.mkdir(parents=True)
    started = time.perf_counter()
    command = [
        sys.executable,
        "-m",
        "benchmarks.run_task037_extra_m6b",
        "m6b-w6a-builder",
        "--run-dir",
        str(run_dir),
        "--legacy-store-dir",
        str(Path(legacy_store_dir).resolve()),
        "--w5-raw-dir",
        str(Path(w5_raw_dir).resolve()),
        "--jit-cache-source",
        str(Path(jit_cache_source).resolve()),
        "--expected-source-sha",
        expected_source_sha,
    ]
    process = h2b._monitor_phase(
        watchdog_dir,
        M6B_W6A_PHASE,
        command,
        M6B_W6A_BUILDER_TIMEOUT_SECONDS,
        M6B_W6A_WATCHDOG_RSS_LIMIT_BYTES,
    )
    drain = h2b._bounded_process_drain(process)
    source_end = h2b._light_source()
    timeline_name = f"{M6B_W6A_PHASE}_timeline.jsonl"
    stdout_name = f"{M6B_W6A_PHASE}_stdout.txt"
    root_name = f"{M6B_W6A_PHASE}_root_pid.json"
    raw_names = [
        "w6a_summary.json",
        "w6a_progress.jsonl",
        "sparse_range_store/manifest.json",
        "sparse_range_store/z_data.npy",
        "sparse_range_store/z_indices.npy",
        "sparse_range_store/z_indptr.npy",
        "sparse_range_store/gram.npy",
        "sparse_range_store/r_factor.npy",
        *(f"m6b_w6a_residual_iter{iteration}.npy" for iteration in M6B_W6A_W5_RESIDUAL_ITERATIONS),
    ]
    inventory = {
        "raw": [_artifact(run_dir, name) for name in raw_names],
        "watchdog": [_artifact(watchdog_dir, name) for name in (timeline_name, stdout_name, root_name)],
    }
    payload = {
        "schema": M6B_W6A_WATCHDOG_SCHEMA,
        "phase": M6B_W6A_PHASE,
        "status": "measurement_complete" if process.get("return_code") == 0 and process.get("termination") is None else "gate_failed",
        "process": process,
        "drain": drain,
        "source_at_start": source_start,
        "source_at_end": source_end,
        "source_end_clean": bool(_m6b_w6a_source_valid(source_end) and source_end.get("source_commit_full_sha") == expected_source_sha),
        "resource_limits": {
            "timeout_seconds": M6B_W6A_BUILDER_TIMEOUT_SECONDS,
            "watchdog_rss_bytes": M6B_W6A_WATCHDOG_RSS_LIMIT_BYTES,
            "completion_peak_rss_bytes": M6B_W6A_BUILDER_RSS_LIMIT_BYTES,
            "swap_bytes": 0,
        },
        "raw_dir": str(run_dir),
        "watchdog_dir": str(watchdog_dir),
        "command": command,
        "artifact_inventory": inventory,
        "builder_summary": _artifact(run_dir, "w6a_summary.json"),
        "timeline": _m6b_w6a_timeline_valid(watchdog_dir / timeline_name),
        "formal_pass": False,
        "pde_pass": False,
        "elapsed_wall_seconds": float(time.perf_counter() - started),
    }
    _write_json(watchdog_dir / "w6a_watchdog_summary.json", _attach_evidence(payload))
    return 0 if payload["status"] == "measurement_complete" else 1


def _run_m6b_w8a_builder(
    run_dir: Path,
    w6a_raw_dir: Path,
    jit_cache_source: Path,
    expected_source_sha: str,
) -> int:
    """Build the fixed 140-column W8A bubbles over frozen W6A data."""

    import gc
    import shutil
    import time

    import numpy as np
    from mpi4py import MPI

    h2b = __import__("benchmarks.run_task037_extra_h2b", fromlist=["*"])
    m6a = __import__("benchmarks.run_task037_extra_m6", fromlist=["*"])
    from benchmarks.run_task037_extra_h2 import _jsonable
    from src.solvers.hcurl_fullspace_dtn import (
        build_fullspace_dtn_action,
        build_fullspace_dtn_carrier_from_surface,
    )
    from src.solvers.hcurl_h2b_m6b_shifted_patch_pc import (
        M6BNumpyOuterActionBridge,
        build_m6b_outer_mat,
        build_m6b_volume_form,
    )
    from src.solvers.hcurl_m6b_w8a_z_bubble_range import (
        W8AMultiOrderRangeDiagnostic,
        build_w8a_bubble_columns_from_fe,
        load_w6a_legacy_for_w8a,
    )
    from src.solvers.hcurl_rank_one_mpc_action import build_task037_extra_h1r2_mpc_action

    run_dir = Path(run_dir).resolve()
    w6a_raw_dir = Path(w6a_raw_dir).resolve()
    jit_cache_source = Path(jit_cache_source).resolve()
    if run_dir.exists():
        raise FileExistsError(f"W8A builder refuses existing directory: {run_dir}")
    if MPI.COMM_WORLD.size != 1:
        raise RuntimeError("W8A builder is fixed to MPI1")
    w6a_authority = _m6b_w8a_w6a_authority(w6a_raw_dir)
    legacy_store_dir = _m6b_w8a_legacy_store_dir(w6a_raw_dir)
    w5_authority = _m6b_w6a_w5_compact_authority()
    if not jit_cache_source.is_dir():
        raise FileNotFoundError("W8A frozen authority path is missing")
    frozen_compiler = w5_authority["factor_compiler"]
    h2a = h2b._lazy_h2a()
    runtime_identity = _m6b_runtime_identity(
        h2b,
        h2a,
        MPI.COMM_WORLD,
        compiler_probe=False,
        compiler=frozen_compiler,
    )
    if not _m6b_w6a_runtime_valid(runtime_identity, frozen_compiler=frozen_compiler):
        raise RuntimeError("W8A qualified runtime identity is not closed")
    source_start = h2b._light_source()
    if source_start.get("source_commit_full_sha") != expected_source_sha or not _m6b_w6a_source_valid(source_start):
        raise RuntimeError("W8A builder source identity is not clean or expected")

    run_dir.mkdir(parents=True)
    cache_dir = run_dir / "jit_cache"
    shutil.copytree(jit_cache_source, cache_dir)
    progress_path = run_dir / "w8a_progress.jsonl"
    started = time.perf_counter()

    def emit(event: str, **fields: Any) -> None:
        _m6b_w8a_progress_emit(
            progress_path,
            event,
            elapsed_wall_seconds=float(time.perf_counter() - started),
            **fields,
        )
        print(json.dumps({"event": event, **fields}, sort_keys=True), flush=True)

    source_cache_before = _m6b_w6a_cache_record(h2b, jit_cache_source)
    target_cache_before = _m6b_w6a_cache_record(h2b, cache_dir)
    if source_cache_before["inventory_sha256"] != M6B_W8A_W6A_JIT_INVENTORY_SHA256:
        raise ValueError("W8A JIT source inventory authority differs")
    if source_cache_before != target_cache_before:
        raise ValueError("W8A copied JIT cache differs from source")
    emit("authority_validated", source_sha=expected_source_sha)

    physical_action = dtn_action = outer_mat = outer_context = None
    bridge = template = None
    surface_assemblers = None
    diagnostic = None
    old_store = None
    try:
        cfg, mesh_data, function_space, floquet, modes = m6a._production_objects(
            run_dir, mesh_name="m6b_w8a_mesh"
        )
        identity = m6a._p6_identity(mesh_data, function_space, floquet)
        expected_identity = {
            "global_cells": M6B_GLOBAL_CELLS,
            "local_cells": M6B_GLOBAL_CELLS,
            "local_nloc": M6B_LOCAL_NLOC,
            "global_rows": M6B_GLOBAL_ROWS,
            "constraint_count": M6B_CONSTRAINTS,
        }
        if identity != expected_identity:
            raise ValueError(f"W8A p6/h10 identity differs: {identity}")
        emit("mesh_ready", global_cells=identity["global_cells"])
        emit("space_ready", global_rows=identity["global_rows"])
        emit("floquet_mpc_ready", constraint_count=identity["constraint_count"])

        physical_ufl, epsilon, abs_epsilon, beta, tag_coverage = build_m6b_volume_form(
            function_space, mesh_data, cfg, beta=0.0
        )
        physical_action = build_task037_extra_h1r2_mpc_action(
            physical_ufl,
            floquet.mpc,
            task037_extra_h1r2=True,
            jit_options=h2b._expected_jit_options(cache_dir),
        )
        target_after_forward = _m6b_w6a_cache_record(h2b, cache_dir)
        source_after_forward = _m6b_w6a_cache_record(h2b, jit_cache_source)
        if target_after_forward != target_cache_before or source_after_forward != source_cache_before:
            raise ValueError("W8A forward form changed the frozen JIT cache")
        emit("cache_ready", inventory_sha256=target_after_forward["inventory_sha256"])
        surface_assemblers = m6a._surface_assemblers(
            function_space, mesh_data, cfg, modes, cache_dir
        )
        dtn_carrier = build_fullspace_dtn_carrier_from_surface(
            modes, surface_assemblers, floquet.mpc, cfg, expected_mode_count=80
        )
        dtn_action = build_fullspace_dtn_action(dtn_carrier, comm=MPI.COMM_WORLD)
        outer_mat, outer_context = build_m6b_outer_mat(
            physical_action,
            dtn_action,
            owned_rows=M6B_GLOBAL_ROWS,
            global_rows=M6B_GLOBAL_ROWS,
            comm=MPI.COMM_WORLD,
        )
        template = outer_mat.createVecRight()
        ownership = tuple(int(value) for value in template.getOwnershipRange())
        bridge = M6BNumpyOuterActionBridge(outer_context, template)
        emit("outer_ready", tag_coverage=tag_coverage)
        target_after_surface = _m6b_w6a_cache_record(h2b, cache_dir)
        source_after_surface = _m6b_w6a_cache_record(h2b, jit_cache_source)
        if target_after_surface != target_after_forward or source_after_surface != source_cache_before:
            raise ValueError("W8A surface construction changed the frozen JIT cache")

        legacy_identity, legacy_arrays, old_store = load_w6a_legacy_for_w8a(legacy_store_dir)
        legacy = {
            **legacy_identity,
            **legacy_arrays,
            "az_store": old_store,
        }
        emit("legacy_basis_ready", columns=M6B_W8A_LEGACY_COLUMNS)
        emit("bubble_spec_ready", columns=M6B_W8A_ADDED_COLUMNS, intervals=M6B_W8A_INTERVALS)
        added_columns, fe_audit = build_w8a_bubble_columns_from_fe(
            function_space,
            mesh_data,
            floquet,
            template,
            cfg,
            ownership_range=ownership,
        )
        old_retained = int(
            legacy_arrays["z_data"].nbytes
            + legacy_arrays["z_indices"].nbytes
            + legacy_arrays["z_indptr"].nbytes
            + legacy_arrays["r_factor"].nbytes
        )
        old_work = int(w6a_authority["summary"]["carrier_audit"]["bounded_work_bytes"])
        new_nnz = int(legacy_arrays["z_data"].size + sum(column.indices.size for column in added_columns))
        new_z_bytes = int(new_nnz * (16 + 4) + (M6B_W8A_COLUMNS + 1) * 4)
        new_r_bytes = int(M6B_W8A_COLUMNS * M6B_W8A_COLUMNS * 16)
        new_retained = new_z_bytes + new_r_bytes + M6B_W6A_MANIFEST_RESERVE_BYTES
        new_work = int(5 * M6B_GLOBAL_ROWS * 16)
        if new_z_bytes + new_r_bytes > M6B_W8A_RETAINED_LIMIT_BYTES:
            raise ValueError("W8A retained sparse Z+R exceeds the fixed gate")
        prediction = _m6b_w8a_predicted_live_set(
            old_retained_bytes=old_retained,
            new_retained_bytes=new_retained,
            old_work_bytes=old_work,
            new_work_bytes=new_work,
        )
        if prediction["gate"] is not True:
            raise ValueError("W8A predicted live set exceeds the fixed gate")

        def action(values: np.ndarray) -> np.ndarray:
            return bridge.apply(values)

        def progress(event: str, first: int, second: int) -> None:
            if event == "column_progress":
                emit("column_progress", completed=first, total=second)
                if first == M6B_W8A_ADDED_COLUMNS:
                    emit("bubble_columns_ready", completed=first, total=second)
            elif event == "repeat_ready":
                emit("repeat_ready", column_index=first, completed_repeats=second, total_repeats=len(M6B_W8A_REPEAT_COLUMNS))
            elif event == "az_ready":
                emit("az_ready", completed=first, total=second)
            elif event == "gram_ready":
                emit("gram_ready", completed=first, total=second)
            elif event == "legacy_ready":
                return
            else:
                raise ValueError(f"W8A progress event is unknown: {event}")

        diagnostic = W8AMultiOrderRangeDiagnostic.from_legacy_and_added(
            legacy,
            added_columns,
            action,
            global_rows=M6B_GLOBAL_ROWS,
            ownership_range=ownership,
            scratch_dir=run_dir / "az_scratch",
            identity={
                "source_sha": expected_source_sha,
                "operator_identity": "A=Kcurl-k0^2*M_epsilon+A_DtN",
                "legacy_w6a_manifest_sha256": legacy["manifest_file_sha256"],
                "legacy_w6a_az_column_sha256_aggregate": legacy["az_column_sha256_aggregate"],
                "fine_space": "uncondensed_fullspace",
                "global_matrix": False,
                "static_condensation": False,
                "trace_slab_pc": False,
                "dtn_matrix_free": True,
            },
            progress=progress,
        )
        old_store = None
        diagnostic.save(run_dir / "sparse_range_store")
        del added_columns, legacy, legacy_arrays
        gc.collect()
        source_final = _m6b_w6a_cache_record(h2b, jit_cache_source)
        target_final = _m6b_w6a_cache_record(h2b, cache_dir)
        source_end = h2b._light_source()
        summary = {
            "schema": M6B_W8A_SCHEMA,
            "status": "builder_complete",
            "formal_pass": False,
            "pde_pass": False,
            "official_rta": False,
            "qualification": "pre_formal_w8a_builder_measurement",
            "runtime_identity": runtime_identity,
            "source_at_start": source_start,
            "source_at_end": source_end,
            "expected_source_sha": expected_source_sha,
            "w6a_authority": {
                "summary": w6a_authority["artifact"],
                "summary_sha256": M6B_W8A_W6A_SUMMARY_SHA256,
                "producer_source_sha": M6B_W8A_W6A_SOURCE_SHA,
                "store_manifest": _artifact(legacy_store_dir, "manifest.json"),
            },
            "w5_compact_authority": {
                "path": w5_authority["path"],
                "file_sha256": w5_authority["file_sha256"],
                "producer_source_sha": M6B_W8A_W5_SOURCE_SHA,
            },
            "scope": _m6b_w8a_scope(prediction=prediction),
            "prediction": prediction,
            "p6_identity": identity,
            "fe_audit": fe_audit,
            "legacy_z_identity": diagnostic.legacy_z_identity,
            "store_manifest_artifact": _artifact(run_dir, "sparse_range_store/manifest.json"),
            "carrier_audit": diagnostic.audit,
            "action_audit": {
                "frozen_legacy_action_count": 0,
                "new_base_action_count": M6B_W8A_ADDED_COLUMNS,
                "selected_repeat_action_count": len(M6B_W8A_REPEAT_COLUMNS),
                "total_new_action_count": M6B_W8A_ADDED_COLUMNS + len(M6B_W8A_REPEAT_COLUMNS),
                "outer_forward_apply_count": bridge.audit["forward_apply_count"],
                "bridge": bridge.audit,
                "outer_context": _jsonable(dict(outer_context.audit)),
                "physical_action": _jsonable(dict(physical_action.audit)),
                "dtn_action": _jsonable(dict(dtn_action.audit)),
            },
            "jit_cache": {
                "source": str(jit_cache_source),
                "target": str(cache_dir),
                "source_before": source_cache_before,
                "source_after_forward": source_after_forward,
                "source_after_surface": source_after_surface,
                "source_final": source_final,
                "target_before": target_cache_before,
                "target_after_forward": target_after_forward,
                "target_after_surface": target_after_surface,
                "target_final": target_final,
                "source_unchanged": source_final == source_cache_before,
                "target_frozen_unchanged": target_final == target_after_surface,
            },
            "architecture": {
                "fine_space": "uncondensed_fullspace",
                "global_matrix": False,
                "augmented_matrix": False,
                "static_condensation": False,
                "trace_slab_pc": False,
                "schur": False,
                "explicit_C_materialized_count": 0,
                "explicit_D_materialized_count": 0,
                "dtn_matrix_free": True,
                "dense_z_retained": False,
                "dense_az_retained": False,
                "az_builder_only": True,
                "az_production_retained": False,
            },
            "progress_artifact": _artifact(run_dir, "w8a_progress.jsonl"),
            "progress": None,
            "builder_limits": {
                "timeout_seconds": M6B_W8A_TIMEOUT_SECONDS,
                "completed_peak_rss_bytes": M6B_W8A_BUILDER_RSS_LIMIT_BYTES,
                "watchdog_rss_bytes": M6B_W8A_WATCHDOG_RSS_LIMIT_BYTES,
                "swap_bytes": M6B_SWAP_LIMIT_BYTES,
                "formal_peak_gate": "not_measured",
            },
            "elapsed_wall_seconds": float(time.perf_counter() - started),
        }
        emit("summary_ready")
        summary["progress"] = _m6b_w8a_progress_valid(progress_path)
        _write_json(run_dir / "w8a_summary.json", _attach_evidence(summary))
        return 0
    finally:
        if diagnostic is not None:
            diagnostic.close()
        elif old_store is not None:
            old_store.close()
        if bridge is not None:
            bridge.destroy()
        if template is not None:
            template.destroy()
        if outer_mat is not None:
            outer_mat.destroy()
        if outer_context is not None:
            outer_context.destroy()
        if dtn_action is not None:
            dtn_action.destroy()
        if physical_action is not None:
            physical_action.destroy()
        if surface_assemblers is not None:
            for assembler in surface_assemblers.values():
                destroy = getattr(assembler, "destroy", None)
                if destroy is not None:
                    destroy()
        gc.collect()


def _run_m6b_w8a_companion(
    run_dir: Path,
    w8a_raw_dir: Path,
    w6a_raw_dir: Path,
    jit_cache_source: Path,
    expected_source_sha: str,
) -> int:
    """Re-establish W8A's FE/operator identity with three fixed actions."""

    import gc
    import shutil
    import time

    import numpy as np
    from mpi4py import MPI

    h2b = __import__("benchmarks.run_task037_extra_h2b", fromlist=["*"])
    m6a = __import__("benchmarks.run_task037_extra_m6", fromlist=["*"])
    from benchmarks.run_task037_extra_h2 import _jsonable
    from src.solvers.hcurl_fullspace_dtn import (
        build_fullspace_dtn_action,
        build_fullspace_dtn_carrier_from_surface,
    )
    from src.solvers.hcurl_h2b_m6b_shifted_patch_pc import (
        M6BNumpyOuterActionBridge,
        build_m6b_outer_mat,
        build_m6b_volume_form,
    )
    from src.solvers.hcurl_m6b_w8a_z_bubble_range import (
        build_w8a_bubble_columns_from_fe,
        _array_sha256,
    )
    from src.solvers.disk_backed_flexible_gmres import RawPositionalColumnStore
    from src.solvers.hcurl_rank_one_mpc_action import build_task037_extra_h1r2_mpc_action

    run_dir = Path(run_dir).resolve()
    w8a_raw_dir = Path(w8a_raw_dir).resolve()
    w6a_raw_dir = Path(w6a_raw_dir).resolve()
    jit_cache_source = Path(jit_cache_source).resolve()
    if run_dir.exists():
        raise FileExistsError(f"W8A companion refuses existing directory: {run_dir}")
    if MPI.COMM_WORLD.size != 1:
        raise RuntimeError("W8A companion is fixed to MPI1")
    if expected_source_sha == M6B_W8A_RECOVERY_PRODUCER_SHA:
        raise ValueError("W8A companion requires a post-producer source")
    if w8a_raw_dir != (ROOT / M6B_W8A_RECOVERY_RAW_RELATIVE_PATH).resolve():
        raise ValueError("W8A companion requires the frozen W8A producer raw")
    frozen_files = _m6b_w8a_recovery_artifacts(
        w8a_raw_dir, Path(M6B_W8A_RECOVERY_WATCHDOG_PATH)
    )
    if frozen_files["pass"] is not True:
        raise ValueError("W8A companion frozen producer artifacts differ")
    w6a_authority = _m6b_w8a_w6a_authority(w6a_raw_dir)
    _m6b_w8a_legacy_store_dir(w6a_raw_dir)
    w5_authority = _m6b_w6a_w5_compact_authority()
    if not jit_cache_source.is_dir():
        raise FileNotFoundError("W8A companion JIT source is missing")
    frozen_compiler = w5_authority["factor_compiler"]
    h2a = h2b._lazy_h2a()
    runtime_identity = _m6b_runtime_identity(
        h2b,
        h2a,
        MPI.COMM_WORLD,
        compiler_probe=False,
        compiler=frozen_compiler,
    )
    if not _m6b_w6a_runtime_valid(runtime_identity, frozen_compiler=frozen_compiler):
        raise RuntimeError("W8A companion runtime identity is not closed")
    source_start = h2b._light_source()
    if (
        source_start.get("source_commit_full_sha") != expected_source_sha
        or not _m6b_w6a_source_valid(source_start)
    ):
        raise RuntimeError("W8A companion source identity is not clean or expected")

    run_dir.mkdir(parents=True)
    cache_dir = run_dir / "jit_cache"
    shutil.copytree(jit_cache_source, cache_dir)
    progress_path = run_dir / "w8a_companion_progress.jsonl"
    started = time.perf_counter()

    def emit(event: str, **fields: Any) -> None:
        _m6b_w8a_companion_progress_emit(
            progress_path,
            event,
            elapsed_wall_seconds=float(time.perf_counter() - started),
            **fields,
        )
        print(json.dumps({"event": event, **fields}, sort_keys=True), flush=True)

    source_cache_before = _m6b_w6a_cache_record(h2b, jit_cache_source)
    target_cache_before = _m6b_w6a_cache_record(h2b, cache_dir)
    if (
        source_cache_before["inventory_sha256"] != M6B_W8A_W6A_JIT_INVENTORY_SHA256
        or source_cache_before != target_cache_before
    ):
        raise ValueError("W8A companion JIT cache authority differs")
    emit("authority_validated", source_sha=expected_source_sha)

    physical_action = dtn_action = outer_mat = outer_context = None
    bridge = template = None
    surface_assemblers = None
    old_az_store = None
    try:
        cfg, mesh_data, function_space, floquet, modes = m6a._production_objects(
            run_dir, mesh_name="m6b_w8a_companion_mesh"
        )
        identity = m6a._p6_identity(mesh_data, function_space, floquet)
        expected_identity = {
            "global_cells": M6B_GLOBAL_CELLS,
            "local_cells": M6B_GLOBAL_CELLS,
            "local_nloc": M6B_LOCAL_NLOC,
            "global_rows": M6B_GLOBAL_ROWS,
            "constraint_count": M6B_CONSTRAINTS,
        }
        if identity != expected_identity:
            raise ValueError(f"W8A companion p6 identity differs: {identity}")
        emit("mesh_ready", global_cells=identity["global_cells"])
        emit("space_ready", global_rows=identity["global_rows"])
        emit("floquet_mpc_ready", constraint_count=identity["constraint_count"])

        physical_ufl, epsilon, abs_epsilon, beta, tag_coverage = build_m6b_volume_form(
            function_space, mesh_data, cfg, beta=0.0
        )
        physical_action = build_task037_extra_h1r2_mpc_action(
            physical_ufl,
            floquet.mpc,
            task037_extra_h1r2=True,
            jit_options=h2b._expected_jit_options(cache_dir),
        )
        source_after_forward = _m6b_w6a_cache_record(h2b, jit_cache_source)
        target_after_forward = _m6b_w6a_cache_record(h2b, cache_dir)
        if source_after_forward != source_cache_before or target_after_forward != target_cache_before:
            raise ValueError("W8A companion forward form changed the frozen JIT cache")
        emit("cache_ready", inventory_sha256=target_after_forward["inventory_sha256"])
        surface_assemblers = m6a._surface_assemblers(
            function_space, mesh_data, cfg, modes, cache_dir
        )
        dtn_carrier = build_fullspace_dtn_carrier_from_surface(
            modes, surface_assemblers, floquet.mpc, cfg, expected_mode_count=80
        )
        dtn_action = build_fullspace_dtn_action(dtn_carrier, comm=MPI.COMM_WORLD)
        outer_mat, outer_context = build_m6b_outer_mat(
            physical_action,
            dtn_action,
            owned_rows=M6B_GLOBAL_ROWS,
            global_rows=M6B_GLOBAL_ROWS,
            comm=MPI.COMM_WORLD,
        )
        template = outer_mat.createVecRight()
        ownership = tuple(int(value) for value in template.getOwnershipRange())
        bridge = M6BNumpyOuterActionBridge(outer_context, template)
        emit("outer_ready", tag_coverage=tag_coverage)

        emit("bubble_spec_ready", columns=M6B_W8A_ADDED_COLUMNS, intervals=M6B_W8A_INTERVALS)
        columns, fe_audit = build_w8a_bubble_columns_from_fe(
            function_space,
            mesh_data,
            floquet,
            template,
            cfg,
            ownership_range=ownership,
        )
        if not _m6b_w8a_fe_audit_valid(fe_audit):
            raise ValueError("W8A companion FE audit is not closed")
        del columns
        gc.collect()
        emit("fe_audit_ready", column_count=M6B_W8A_ADDED_COLUMNS)

        manifest = _read_json(w8a_raw_dir / "sparse_range_store/manifest.json")
        arrays = manifest.get("arrays") if isinstance(manifest, Mapping) else None
        if not isinstance(arrays, Mapping):
            raise ValueError("W8A companion sparse authority is missing")
        z_data = np.load(w8a_raw_dir / "sparse_range_store/z_data.npy", mmap_mode="r", allow_pickle=False)
        z_indices = np.load(w8a_raw_dir / "sparse_range_store/z_indices.npy", mmap_mode="r", allow_pickle=False)
        z_indptr = np.load(w8a_raw_dir / "sparse_range_store/z_indptr.npy", mmap_mode="r", allow_pickle=False)
        if (
            z_data.dtype != np.dtype(np.complex128)
            or z_indices.dtype != np.dtype(np.int32)
            or z_indptr.dtype != np.dtype(np.int32)
            or z_indptr.shape != (M6B_W8A_COLUMNS + 1,)
        ):
            raise ValueError("W8A companion sparse authority arrays are invalid")
        old_az_path = w8a_raw_dir / "az_scratch/new_columns.bin"
        if _artifact(w8a_raw_dir, "az_scratch/new_columns.bin").get("sha256") != M6B_W8A_RECOVERY_RAW_FILE_SHA256["az_scratch/new_columns.bin"]:
            raise ValueError("W8A companion old AZ scratch authority differs")
        old_az_store = RawPositionalColumnStore.open_readonly(
            old_az_path, M6B_GLOBAL_ROWS, M6B_W8A_ADDED_COLUMNS
        )
        sentinel_actions: list[dict[str, Any]] = []
        old_az_buffer = np.empty(M6B_GLOBAL_ROWS, dtype=np.complex128)
        for column in M6B_W8A_COMPANION_SENTINEL_COLUMNS:
            first, last = int(z_indptr[column]), int(z_indptr[column + 1])
            vector = np.zeros(M6B_GLOBAL_ROWS, dtype=np.complex128)
            vector[z_indices[first:last]] = z_data[first:last]
            observed = np.asarray(bridge.apply(vector))
            if observed.shape != (M6B_GLOBAL_ROWS,) or observed.dtype != np.dtype(np.complex128) or not np.all(np.isfinite(observed)):
                raise ValueError(f"W8A companion sentinel {column} is invalid")
            old_az_store.read_column(column - M6B_W8A_LEGACY_COLUMNS, old_az_buffer)
            relative_error = float(
                np.linalg.norm(observed - old_az_buffer)
                / max(np.linalg.norm(old_az_buffer), np.finfo(float).tiny)
            )
            if not np.isfinite(relative_error) or relative_error > 1.0e-11:
                raise ValueError(f"W8A companion sentinel {column} differs from frozen AZ")
            sentinel_actions.append({
                "column_index": column,
                "input_array_sha256": _array_sha256(vector),
                "old_az_array_sha256": _array_sha256(old_az_buffer),
                "output_array_sha256": _array_sha256(observed),
                "relative_error": relative_error,
                "finite": True,
            })
            del vector, observed
        del old_az_buffer, z_data, z_indices, z_indptr, arrays, manifest
        gc.collect()
        emit("sentinel_ready", columns=list(M6B_W8A_COMPANION_SENTINEL_COLUMNS), action_count=3)

        source_after_surface = _m6b_w6a_cache_record(h2b, jit_cache_source)
        target_after_surface = _m6b_w6a_cache_record(h2b, cache_dir)
        source_final = _m6b_w6a_cache_record(h2b, jit_cache_source)
        target_final = _m6b_w6a_cache_record(h2b, cache_dir)
        if source_after_surface != source_cache_before or target_after_surface != target_after_forward or source_final != source_after_surface or target_final != target_after_surface:
            raise ValueError("W8A companion surface path changed the frozen JIT cache")
        old_summary = w6a_authority["summary"]
        manifest = _read_json(w8a_raw_dir / "sparse_range_store/manifest.json")
        new_retained_bytes = int(
            sum(int(manifest["arrays"][name]["nbytes"]) for name in ("z_data", "z_indices", "z_indptr", "r_factor"))
            + M6B_W6A_MANIFEST_RESERVE_BYTES
        )
        prediction = _m6b_w8a_predicted_live_set(
            old_retained_bytes=int(old_summary["carrier_audit"]["retained_z_r_bytes"]),
            new_retained_bytes=new_retained_bytes,
            old_work_bytes=int(old_summary["carrier_audit"]["bounded_work_bytes"]),
            new_work_bytes=int(5 * M6B_GLOBAL_ROWS * 16),
        )
        source_end = h2b._light_source()
        action_audit = {
            "frozen_legacy_action_count": 0,
            "new_base_action_count": 0,
            "selected_repeat_action_count": len(M6B_W8A_COMPANION_SENTINEL_COLUMNS),
            "total_new_action_count": len(M6B_W8A_COMPANION_SENTINEL_COLUMNS),
            "outer_forward_apply_count": bridge.audit["forward_apply_count"],
            "bridge": bridge.audit,
            "outer_context": _jsonable(dict(outer_context.audit)),
            "physical_action": _jsonable(dict(physical_action.audit)),
            "dtn_action": _jsonable(dict(dtn_action.audit)),
        }
        architecture = {
            "fine_space": "uncondensed_fullspace",
            "global_matrix": False,
            "augmented_matrix": False,
            "static_condensation": False,
            "trace_slab_pc": False,
            "schur": False,
            "dtn_matrix_free": True,
            "dense_z_retained": False,
            "dense_az_retained": False,
            "az_builder_only": True,
            "az_production_retained": False,
            "explicit_C_materialized_count": 0,
            "explicit_D_materialized_count": 0,
        }
        checks = {
            "source": _m6b_w6a_source_valid(source_end) and source_end.get("source_commit_full_sha") == expected_source_sha,
            "p6": identity == expected_identity,
            "runtime": _m6b_w6a_runtime_valid(runtime_identity, frozen_compiler=frozen_compiler),
            "fe": _m6b_w8a_fe_audit_valid(fe_audit),
            "action": _m6b_w8a_action_audit_valid(action_audit, expected_new_base=0, expected_repeat=3, expected_total=3),
            "architecture": _m6b_w8a_companion_architecture_valid(architecture),
            "sentinel": len(sentinel_actions) == 3 and all(
                item["finite"] and item["relative_error"] <= 1.0e-11
                for item in sentinel_actions
            ),
            "prediction": prediction["gate"] is True,
            "jit": source_final == source_cache_before and target_final == target_after_surface,
        }
        companion_gate_pass = all(checks.values())
        summary = {
            "schema": M6B_W8A_COMPANION_SCHEMA,
            "phase": M6B_W8A_COMPANION_PHASE,
            "status": "companion_complete" if companion_gate_pass else "gate_failed",
            "formal_pass": False,
            "pde_pass": False,
            "official_rta": False,
            "companion_gate_pass": companion_gate_pass,
            "source_at_start": source_start,
            "source_at_end": source_end,
            "expected_source_sha": expected_source_sha,
            "raw_dir": str(run_dir),
            "watchdog_dir": None,
            "runtime_identity": runtime_identity,
            "p6_identity": identity,
            "w6a_authority": w6a_authority["artifact"],
            "w8a_raw_dir": str(w8a_raw_dir),
            "w8a_artifacts": frozen_files["inventory"],
            "scope": {
                "schema": M6B_W8A_COMPANION_SCHEMA,
                "beta": 1.0,
                "fine_space": "uncondensed_fullspace",
                "sentinel_columns": list(M6B_W8A_COMPANION_SENTINEL_COLUMNS),
                "sentinel_action_count": 3,
                "old_producer_action_count": 143,
                "old_producer_action_count_source": "frozen_w8a_manifest_only",
                "global_matrix": False,
                "static_condensation": False,
                "trace_slab_pc": False,
                "dtn_matrix_free": True,
            },
            "prediction": prediction,
            "fe_audit": fe_audit,
            "action_audit": action_audit,
            "architecture": architecture,
            "sentinel_actions": sentinel_actions,
            "checks": checks,
            "jit_cache": {
                "source": str(jit_cache_source),
                "target": str(cache_dir),
                "source_before": source_cache_before,
                "source_after_forward": source_after_forward,
                "source_after_surface": source_after_surface,
                "source_final": source_final,
                "target_before": target_cache_before,
                "target_after_forward": target_after_forward,
                "target_after_surface": target_after_surface,
                "target_final": target_final,
                "source_unchanged": source_final == source_cache_before,
                "target_frozen_unchanged": target_final == target_after_surface,
            },
            "progress": None,
            "elapsed_wall_seconds": float(time.perf_counter() - started),
        }
        emit("summary_ready")
        summary["progress"] = _m6b_w8a_companion_progress_valid(progress_path)
        _write_json(run_dir / "w8a_companion_summary.json", _attach_evidence(summary))
        return 0 if companion_gate_pass else 1
    finally:
        if old_az_store is not None:
            old_az_store.close()
        if bridge is not None:
            bridge.destroy()
        if template is not None:
            template.destroy()
        if outer_mat is not None:
            outer_mat.destroy()
        if outer_context is not None:
            outer_context.destroy()
        if dtn_action is not None:
            dtn_action.destroy()
        if physical_action is not None:
            physical_action.destroy()
        if surface_assemblers is not None:
            for assembler in surface_assemblers.values():
                destroy = getattr(assembler, "destroy", None)
                if destroy is not None:
                    destroy()
        gc.collect()


def _run_m6b_w8a_companion_watchdog(
    run_dir: Path,
    watchdog_dir: Path,
    w8a_raw_dir: Path,
    w6a_raw_dir: Path,
    jit_cache_source: Path,
    expected_source_sha: str,
) -> int:
    """Run the three-action companion under the standard process monitor."""

    import time

    h2b = __import__("benchmarks.run_task037_extra_h2b", fromlist=["*"])
    run_dir, watchdog_dir = Path(run_dir).resolve(), Path(watchdog_dir).resolve()
    w8a_raw_dir = Path(w8a_raw_dir).resolve()
    w6a_raw_dir = Path(w6a_raw_dir).resolve()
    jit_cache_source = Path(jit_cache_source).resolve()
    if run_dir.exists() or watchdog_dir.exists():
        raise FileExistsError("W8A companion watchdog refuses existing paths")
    _m6b_w8a_legacy_store_dir(w6a_raw_dir)
    source_start = h2b._light_source()
    if source_start.get("source_commit_full_sha") != expected_source_sha or not _m6b_w6a_source_valid(source_start):
        raise RuntimeError("W8A companion watchdog source identity is not clean or expected")
    watchdog_dir.mkdir(parents=True)
    command = [
        sys.executable, "-m", "benchmarks.run_task037_extra_m6b", "m6b-w8a-companion",
        "--run-dir", str(run_dir), "--w8a-raw-dir", str(w8a_raw_dir),
        "--w6a-raw-dir", str(w6a_raw_dir), "--jit-cache-source", str(jit_cache_source),
        "--expected-source-sha", expected_source_sha,
    ]
    started = time.perf_counter()
    process = h2b._monitor_phase(
        watchdog_dir,
        M6B_W8A_COMPANION_PHASE,
        command,
        M6B_W8A_COMPANION_TIMEOUT_SECONDS,
        M6B_W8A_WATCHDOG_RSS_LIMIT_BYTES,
    )
    drain = h2b._bounded_process_drain(process)
    source_end = h2b._light_source()
    timeline_name = f"{M6B_W8A_COMPANION_PHASE}_timeline.jsonl"
    stdout_name = f"{M6B_W8A_COMPANION_PHASE}_stdout.txt"
    root_name = f"{M6B_W8A_COMPANION_PHASE}_root_pid.json"
    summary = _artifact(run_dir, "w8a_companion_summary.json")
    companion = None
    if summary.get("present") is True:
        companion = _read_json(run_dir / "w8a_companion_summary.json")
    payload = {
        "schema": M6B_W8A_COMPANION_WATCHDOG_SCHEMA,
        "phase": M6B_W8A_COMPANION_PHASE,
        "status": "measurement_complete" if process.get("return_code") == 0 and process.get("termination") is None else "gate_failed",
        "process": process,
        "drain": drain,
        "source_at_start": source_start,
        "source_at_end": source_end,
        "source_end_clean": _m6b_w6a_source_valid(source_end) and source_end.get("source_commit_full_sha") == expected_source_sha,
        "resource_limits": {
            "timeout_seconds": M6B_W8A_COMPANION_TIMEOUT_SECONDS,
            "watchdog_rss_bytes": M6B_W8A_WATCHDOG_RSS_LIMIT_BYTES,
            "completion_peak_rss_bytes": M6B_W8A_BUILDER_RSS_LIMIT_BYTES,
            "swap_bytes": M6B_SWAP_LIMIT_BYTES,
        },
        "raw_dir": str(run_dir),
        "watchdog_dir": str(watchdog_dir),
        "w8a_raw_dir": str(w8a_raw_dir),
        "command": command,
        "artifact_inventory": {
            "raw": [_artifact(run_dir, name) for name in ("w8a_companion_summary.json", "w8a_companion_progress.jsonl")],
            "watchdog": [_artifact(watchdog_dir, name) for name in (timeline_name, stdout_name, root_name)],
        },
        "companion_summary": summary,
        "companion_gate_pass": bool(isinstance(companion, Mapping) and companion.get("companion_gate_pass") is True),
        "timeline": _m6b_w8a_timeline_valid(watchdog_dir / timeline_name, phase=M6B_W8A_COMPANION_PHASE),
        "formal_pass": False,
        "pde_pass": False,
        "official_rta": False,
        "elapsed_wall_seconds": float(time.perf_counter() - started),
    }
    _write_json(watchdog_dir / "w8a_companion_watchdog_summary.json", _attach_evidence(payload))
    return 0 if payload["status"] == "measurement_complete" and payload["companion_gate_pass"] else 1


def _m6b_w8a_companion_gate(
    companion_summary_path: Path,
    companion_watchdog_path: Path,
    w6a_raw_dir: Path,
    jit_cache_source: Path,
    expected_source_sha: str,
) -> dict[str, Any]:
    import numpy as np
    from src.solvers.hcurl_m6b_w8a_z_bubble_range import _array_sha256

    checks: dict[str, bool] = {}
    summary: Mapping[str, Any] = {}
    watchdog: Mapping[str, Any] = {}
    try:
        summary_value = _read_json(companion_summary_path)
        watchdog_value = _read_json(companion_watchdog_path)
        if isinstance(summary_value, Mapping):
            summary = summary_value
        if isinstance(watchdog_value, Mapping):
            watchdog = watchdog_value
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError):
        pass
    run_dir = Path(companion_summary_path).resolve().parent
    watchdog_dir = Path(companion_watchdog_path).resolve().parent
    checks["summary"] = bool(
        _evidence_valid(summary)
        and summary.get("schema") == M6B_W8A_COMPANION_SCHEMA
        and summary.get("phase") == M6B_W8A_COMPANION_PHASE
        and summary.get("status") == "companion_complete"
        and summary.get("formal_pass") is False
        and summary.get("pde_pass") is False
        and summary.get("official_rta") is False
        and summary.get("companion_gate_pass") is True
        and summary.get("raw_dir") == str(run_dir)
    )
    checks["source"] = bool(
        _m6b_w6a_source_valid(summary.get("source_at_start"))
        and _m6b_w6a_source_valid(summary.get("source_at_end"))
        and summary.get("source_at_start", {}).get("source_commit_full_sha") == expected_source_sha
        and summary.get("source_at_end", {}).get("source_commit_full_sha") == expected_source_sha
    )
    try:
        w5_authority = _m6b_w6a_w5_compact_authority()
        checks["runtime"] = _m6b_w6a_runtime_valid(
            summary.get("runtime_identity"), frozen_compiler=w5_authority["factor_compiler"]
        )
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError):
        checks["runtime"] = False
    checks["p6"] = summary.get("p6_identity") == {
        "global_cells": M6B_GLOBAL_CELLS,
        "local_cells": M6B_GLOBAL_CELLS,
        "local_nloc": M6B_LOCAL_NLOC,
        "global_rows": M6B_GLOBAL_ROWS,
        "constraint_count": M6B_CONSTRAINTS,
    }
    checks["fe"] = _m6b_w8a_fe_audit_valid(summary.get("fe_audit"))
    checks["architecture"] = _m6b_w8a_companion_architecture_valid(summary.get("architecture"))
    checks["action"] = _m6b_w8a_action_audit_valid(
        summary.get("action_audit"),
        expected_new_base=0,
        expected_repeat=len(M6B_W8A_COMPANION_SENTINEL_COLUMNS),
        expected_total=len(M6B_W8A_COMPANION_SENTINEL_COLUMNS),
    )
    sentinel = summary.get("sentinel_actions")
    checks["sentinel"] = bool(
        isinstance(sentinel, list)
        and len(sentinel) == len(M6B_W8A_COMPANION_SENTINEL_COLUMNS)
        and [item.get("column_index") for item in sentinel if isinstance(item, Mapping)]
        == list(M6B_W8A_COMPANION_SENTINEL_COLUMNS)
        and all(
            isinstance(item, Mapping)
            and item.get("finite") is True
            and _finite_number(item.get("relative_error"))
            and item.get("relative_error") <= 1.0e-11
            and _m6b_w6a_valid_sha(item.get("input_array_sha256"))
            and _m6b_w6a_valid_sha(item.get("old_az_array_sha256"))
            and _m6b_w6a_valid_sha(item.get("output_array_sha256"))
            for item in sentinel
        )
    )
    if checks["sentinel"]:
        try:
            from src.solvers.disk_backed_flexible_gmres import RawPositionalColumnStore

            old_store = RawPositionalColumnStore.open_readonly(
                Path(summary["w8a_raw_dir"]) / "az_scratch/new_columns.bin",
                M6B_GLOBAL_ROWS,
                M6B_W8A_ADDED_COLUMNS,
            )
            buffer = np.empty(M6B_GLOBAL_ROWS, dtype=np.complex128)
            for item in sentinel:
                old_store.read_column(
                    int(item["column_index"]) - M6B_W8A_LEGACY_COLUMNS,
                    buffer,
                )
                if item.get("old_az_array_sha256") != _array_sha256(buffer):
                    checks["sentinel"] = False
                    break
                if not _finite_number(item.get("relative_error")) or item["relative_error"] > 1.0e-11:
                    checks["sentinel"] = False
                    break
            del buffer
            old_store.close()
        except (OSError, TypeError, ValueError, KeyError, IndexError):
            checks["sentinel"] = False
    checks["progress"] = _m6b_w8a_companion_progress_valid(
        run_dir / "w8a_companion_progress.jsonl"
    )["pass"]
    frozen_w8a = _m6b_w8a_recovery_artifacts(
        Path(summary.get("w8a_raw_dir", "")),
        Path(M6B_W8A_RECOVERY_WATCHDOG_PATH),
    )
    checks["frozen_w8a"] = bool(
        summary.get("w8a_raw_dir") == str((ROOT / M6B_W8A_RECOVERY_RAW_RELATIVE_PATH).resolve())
        and frozen_w8a["pass"] is True
        and summary.get("w8a_artifacts") == frozen_w8a["inventory"]
    )
    checks["prediction"] = False
    try:
        w6a_authority = _m6b_w8a_w6a_authority(Path(w6a_raw_dir))
        manifest = _read_json(
            ROOT / M6B_W8A_RECOVERY_RAW_RELATIVE_PATH / "sparse_range_store/manifest.json"
        )
        new_retained = int(
            sum(
                int(manifest["arrays"][name]["nbytes"])
                for name in ("z_data", "z_indices", "z_indptr", "r_factor")
            )
            + M6B_W6A_MANIFEST_RESERVE_BYTES
        )
        expected_prediction = _m6b_w8a_predicted_live_set(
            old_retained_bytes=int(w6a_authority["summary"]["carrier_audit"]["retained_z_r_bytes"]),
            new_retained_bytes=new_retained,
            old_work_bytes=int(w6a_authority["summary"]["carrier_audit"]["bounded_work_bytes"]),
            new_work_bytes=int(5 * M6B_GLOBAL_ROWS * 16),
        )
        checks["prediction"] = summary.get("prediction") == expected_prediction and expected_prediction["gate"] is True
    except (OSError, TypeError, ValueError, KeyError, IndexError, json.JSONDecodeError):
        checks["prediction"] = False
    try:
        h2b = __import__("benchmarks.run_task037_extra_h2b", fromlist=["*"])
        target = Path(summary.get("jit_cache", {}).get("target", ""))
        checks["jit"] = _m6b_w6a_jit_cache_valid(
            summary.get("jit_cache"), h2b, jit_cache_source, target
        )
    except (OSError, TypeError, ValueError, KeyError):
        checks["jit"] = False
    timeline_name = f"{M6B_W8A_COMPANION_PHASE}_timeline.jsonl"
    timeline = _m6b_w8a_timeline_valid(
        watchdog_dir / timeline_name, phase=M6B_W8A_COMPANION_PHASE
    )
    expected_command = [
        sys.executable, "-m", "benchmarks.run_task037_extra_m6b", "m6b-w8a-companion",
        "--run-dir", str(run_dir), "--w8a-raw-dir", summary.get("w8a_raw_dir"),
        "--w6a-raw-dir", str(Path(w6a_raw_dir).resolve()),
        "--jit-cache-source", str(Path(jit_cache_source).resolve()),
        "--expected-source-sha", expected_source_sha,
    ]
    process = watchdog.get("process")
    checks["watchdog"] = bool(
        _evidence_valid(watchdog)
        and watchdog.get("schema") == M6B_W8A_COMPANION_WATCHDOG_SCHEMA
        and watchdog.get("phase") == M6B_W8A_COMPANION_PHASE
        and watchdog.get("status") == "measurement_complete"
        and watchdog.get("raw_dir") == str(run_dir)
        and watchdog.get("watchdog_dir") == str(watchdog_dir)
        and watchdog.get("command") == expected_command
        and _m6b_w6a_source_valid(watchdog.get("source_at_start"))
        and _m6b_w6a_source_valid(watchdog.get("source_at_end"))
        and watchdog.get("source_at_start", {}).get("source_commit_full_sha") == expected_source_sha
        and watchdog.get("source_at_end", {}).get("source_commit_full_sha") == expected_source_sha
        and watchdog.get("source_end_clean") is True
        and watchdog.get("timeline") == timeline
        and watchdog.get("companion_gate_pass") is True
        and watchdog.get("resource_limits") == {
            "timeout_seconds": M6B_W8A_COMPANION_TIMEOUT_SECONDS,
            "watchdog_rss_bytes": M6B_W8A_WATCHDOG_RSS_LIMIT_BYTES,
            "completion_peak_rss_bytes": M6B_W8A_BUILDER_RSS_LIMIT_BYTES,
            "swap_bytes": M6B_SWAP_LIMIT_BYTES,
        }
    )
    drain = watchdog.get("drain")
    checks["resource"] = bool(
        isinstance(process, Mapping)
        and process.get("return_code") == 0
        and process.get("termination") is None
        and type(process.get("peak_rss_bytes")) is int
        and process["peak_rss_bytes"] < M6B_W8A_BUILDER_RSS_LIMIT_BYTES
        and process.get("swap_bytes") == 0
        and isinstance(drain, Mapping)
        and drain.get("gone") is True
        and timeline.get("pass") is True
        and timeline.get("peak_rss_bytes") == process.get("peak_rss_bytes")
        and timeline.get("swap_bytes") == 0
        and timeline.get("compiler_descendant_pids") == []
    )
    raw_inventory = watchdog.get("artifact_inventory", {}).get("raw")
    watchdog_inventory = watchdog.get("artifact_inventory", {}).get("watchdog")
    expected_raw = [_artifact(run_dir, name) for name in ("w8a_companion_summary.json", "w8a_companion_progress.jsonl")]
    expected_watchdog = [_artifact(watchdog_dir, name) for name in (timeline_name, f"{M6B_W8A_COMPANION_PHASE}_stdout.txt", f"{M6B_W8A_COMPANION_PHASE}_root_pid.json")]
    checks["artifacts"] = bool(
        watchdog.get("companion_summary") == _artifact(run_dir, "w8a_companion_summary.json")
        and raw_inventory == expected_raw
        and watchdog_inventory == expected_watchdog
        and all(item.get("present") is True for item in expected_raw + expected_watchdog)
    )
    return {
        "checks": checks,
        "pass": all(checks.values()),
        "summary": summary,
        "watchdog": watchdog,
        "timeline": timeline,
        "prediction": summary.get("prediction"),
    }


def _m6b_w8a_timeline_valid(path: Path, phase: str = M6B_W8A_PHASE) -> dict[str, Any]:
    try:
        records = [
            json.loads(line)
            for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if not records:
            raise ValueError("W8A timeline is empty")
        peak = max(int(record["rss_bytes"]) for record in records)
        swap = max(int(record["swap_bytes"]) for record in records)
        compilers = sorted({int(pid) for record in records for pid in record.get("compiler_descendant_pids", [])})
        return {
            "pass": all(record.get("phase") == phase for record in records)
            and swap == 0
            and compilers == [],
            "record_count": len(records),
            "peak_rss_bytes": peak,
            "swap_bytes": swap,
            "compiler_descendant_pids": compilers,
            "records": records,
        }
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        return {"pass": False, "problems": [f"{type(exc).__name__}:{exc}"]}


def _run_m6b_w8a_watchdog(
    run_dir: Path,
    watchdog_dir: Path,
    w6a_raw_dir: Path,
    jit_cache_source: Path,
    expected_source_sha: str,
) -> int:
    """Run exactly one W8A builder under the repository process monitor."""

    import time

    h2b = __import__("benchmarks.run_task037_extra_h2b", fromlist=["*"])
    run_dir, watchdog_dir = Path(run_dir).resolve(), Path(watchdog_dir).resolve()
    w6a_raw_dir = Path(w6a_raw_dir).resolve()
    jit_cache_source = Path(jit_cache_source).resolve()
    if run_dir.exists() or watchdog_dir.exists():
        raise FileExistsError("W8A watchdog refuses existing paths")
    _m6b_w8a_legacy_store_dir(w6a_raw_dir)
    source_start = h2b._light_source()
    if source_start.get("source_commit_full_sha") != expected_source_sha or not _m6b_w6a_source_valid(source_start):
        raise RuntimeError("W8A watchdog source identity is not clean or expected")
    watchdog_dir.mkdir(parents=True)
    command = [
        sys.executable, "-m", "benchmarks.run_task037_extra_m6b", "m6b-w8a-builder",
        "--run-dir", str(run_dir), "--w6a-raw-dir", str(w6a_raw_dir),
        "--jit-cache-source", str(jit_cache_source), "--expected-source-sha", expected_source_sha,
    ]
    started = time.perf_counter()
    process = h2b._monitor_phase(
        watchdog_dir, M6B_W8A_PHASE, command, M6B_W8A_TIMEOUT_SECONDS, M6B_W8A_WATCHDOG_RSS_LIMIT_BYTES
    )
    drain = h2b._bounded_process_drain(process)
    source_end = h2b._light_source()
    timeline_name = f"{M6B_W8A_PHASE}_timeline.jsonl"
    stdout_name = f"{M6B_W8A_PHASE}_stdout.txt"
    root_name = f"{M6B_W8A_PHASE}_root_pid.json"
    raw_names = [
        "w8a_summary.json", "w8a_progress.jsonl", "sparse_range_store/manifest.json",
        "sparse_range_store/z_data.npy", "sparse_range_store/z_indices.npy",
        "sparse_range_store/z_indptr.npy", "sparse_range_store/gram.npy",
        "sparse_range_store/r_factor.npy",
    ]
    payload = {
        "schema": M6B_W8A_WATCHDOG_SCHEMA,
        "phase": M6B_W8A_PHASE,
        "status": "measurement_complete" if process.get("return_code") == 0 and process.get("termination") is None else "gate_failed",
        "process": process,
        "drain": drain,
        "source_at_start": source_start,
        "source_at_end": source_end,
        "source_end_clean": _m6b_w6a_source_valid(source_end) and source_end.get("source_commit_full_sha") == expected_source_sha,
        "resource_limits": {
            "timeout_seconds": M6B_W8A_TIMEOUT_SECONDS,
            "watchdog_rss_bytes": M6B_W8A_WATCHDOG_RSS_LIMIT_BYTES,
            "completion_peak_rss_bytes": M6B_W8A_BUILDER_RSS_LIMIT_BYTES,
            "swap_bytes": M6B_SWAP_LIMIT_BYTES,
        },
        "raw_dir": str(run_dir),
        "watchdog_dir": str(watchdog_dir),
        "command": command,
        "artifact_inventory": {
            "raw": [_artifact(run_dir, name) for name in raw_names],
            "watchdog": [_artifact(watchdog_dir, name) for name in (timeline_name, stdout_name, root_name)],
        },
        "builder_summary": _artifact(run_dir, "w8a_summary.json"),
        "timeline": _m6b_w8a_timeline_valid(watchdog_dir / timeline_name),
        "formal_pass": False,
        "pde_pass": False,
        "elapsed_wall_seconds": float(time.perf_counter() - started),
    }
    _write_json(watchdog_dir / "w8a_watchdog_summary.json", _attach_evidence(payload))
    return 0 if payload["status"] == "measurement_complete" else 1


def _m6b_w8a_formal_gate(
    raw_dir: Path,
    watchdog: Mapping[str, Any],
    watchdog_dir: Path,
    w6a_raw_dir: Path,
    jit_cache_source: Path,
    expected_source_sha: str,
) -> dict[str, Any]:
    import numpy as np
    from src.solvers.hcurl_m6b_w8a_z_bubble_range import W8AMultiOrderRangeDiagnostic

    summary = _read_json(Path(raw_dir) / "w8a_summary.json")
    action_audit = summary.get("action_audit")
    checks: dict[str, bool] = {}
    try:
        legacy_store_dir = _m6b_w8a_legacy_store_dir(w6a_raw_dir)
        checks["legacy_store"] = True
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError):
        legacy_store_dir = Path(w6a_raw_dir).resolve() / "sparse_range_store"
        checks["legacy_store"] = False
    checks["worker"] = _evidence_valid(summary) and summary.get("schema") == M6B_W8A_SCHEMA and summary.get("status") == "builder_complete"
    checks["source"] = all(
        _m6b_w6a_source_valid(summary.get(key))
        and summary.get(key, {}).get("source_commit_full_sha") == expected_source_sha
        for key in ("source_at_start", "source_at_end")
    )
    checks["scope"] = summary.get("scope") == _m6b_w8a_scope(prediction=summary.get("prediction"))
    checks["p6_identity"] = summary.get("p6_identity") == {
        "global_cells": M6B_GLOBAL_CELLS,
        "local_cells": M6B_GLOBAL_CELLS,
        "local_nloc": M6B_LOCAL_NLOC,
        "global_rows": M6B_GLOBAL_ROWS,
        "constraint_count": M6B_CONSTRAINTS,
    }
    try:
        w5_authority = _m6b_w6a_w5_compact_authority()
        checks["runtime_identity"] = _m6b_w6a_runtime_valid(
            summary.get("runtime_identity"),
            frozen_compiler=w5_authority["factor_compiler"],
        )
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError):
        checks["runtime_identity"] = False
    architecture = summary.get("architecture")
    checks["architecture"] = isinstance(architecture, Mapping) and all(
        architecture.get(key) is value for key, value in {
            "global_matrix": False, "augmented_matrix": False, "static_condensation": False,
            "trace_slab_pc": False, "dtn_matrix_free": True, "dense_z_retained": False,
            "dense_az_retained": False, "az_builder_only": True, "az_production_retained": False,
        }.items()
    ) and architecture.get("explicit_C_materialized_count") == 0 and architecture.get("explicit_D_materialized_count") == 0
    checks["progress"] = _m6b_w8a_progress_valid(Path(raw_dir) / "w8a_progress.jsonl")["pass"]
    checks["artifact_inventory"] = _m6b_w8a_artifact_inventory_valid(
        watchdog.get("artifact_inventory"), raw_dir, watchdog_dir
    )
    checks["action"] = _m6b_w8a_action_audit_valid(action_audit)
    independent_timeline = _m6b_w8a_timeline_valid(
        Path(watchdog_dir).resolve() / f"{M6B_W8A_PHASE}_timeline.jsonl"
    )
    timeline = independent_timeline
    process = watchdog.get("process") if isinstance(watchdog, Mapping) else None
    drain = watchdog.get("drain") if isinstance(watchdog, Mapping) else None
    expected_watchdog_command = [
        sys.executable,
        "-m",
        "benchmarks.run_task037_extra_m6b",
        "m6b-w8a-builder",
        "--run-dir",
        str(Path(raw_dir).resolve()),
        "--w6a-raw-dir",
        str(Path(w6a_raw_dir).resolve()),
        "--jit-cache-source",
        str(Path(jit_cache_source).resolve()),
        "--expected-source-sha",
        expected_source_sha,
    ]
    watchdog_start = watchdog.get("source_at_start") if isinstance(watchdog, Mapping) else None
    watchdog_end = watchdog.get("source_at_end") if isinstance(watchdog, Mapping) else None
    checks["watchdog"] = bool(
        isinstance(watchdog, Mapping)
        and _evidence_valid(watchdog)
        and watchdog.get("schema") == M6B_W8A_WATCHDOG_SCHEMA
        and watchdog.get("phase") == M6B_W8A_PHASE
        and watchdog.get("status") == "measurement_complete"
        and watchdog.get("raw_dir") == str(Path(raw_dir).resolve())
        and watchdog.get("watchdog_dir") == str(Path(watchdog_dir).resolve())
        and watchdog.get("command") == expected_watchdog_command
        and _m6b_w6a_source_valid(watchdog_start)
        and _m6b_w6a_source_valid(watchdog_end)
        and watchdog_start.get("source_commit_full_sha") == expected_source_sha
        and watchdog_end.get("source_commit_full_sha") == expected_source_sha
        and watchdog.get("source_end_clean") is True
        and watchdog.get("timeline") == independent_timeline
        and watchdog.get("resource_limits") == {
            "timeout_seconds": M6B_W8A_TIMEOUT_SECONDS,
            "watchdog_rss_bytes": M6B_W8A_WATCHDOG_RSS_LIMIT_BYTES,
            "completion_peak_rss_bytes": M6B_W8A_BUILDER_RSS_LIMIT_BYTES,
            "swap_bytes": M6B_SWAP_LIMIT_BYTES,
        }
    )
    checks["resource"] = bool(
        isinstance(process, Mapping)
        and process.get("return_code") == 0
        and process.get("termination") is None
        and isinstance(process.get("peak_rss_bytes"), int)
        and process["peak_rss_bytes"] < M6B_W8A_BUILDER_RSS_LIMIT_BYTES
        and process.get("swap_bytes") == 0
        and isinstance(drain, Mapping) and drain.get("gone") is True
        and isinstance(timeline, Mapping) and timeline.get("pass") is True
        and timeline.get("peak_rss_bytes") == process.get("peak_rss_bytes")
        and timeline.get("swap_bytes") == 0
        and timeline.get("compiler_descendant_pids") == []
    )
    checks["prediction"] = False
    checks["store"] = False
    diagnostic = None
    try:
        diagnostic = W8AMultiOrderRangeDiagnostic.load(
            Path(raw_dir) / "sparse_range_store" / "manifest.json",
            legacy_store_dir=legacy_store_dir,
        )
        old_nnz = int(diagnostic.z_indptr[M6B_W8A_LEGACY_COLUMNS])
        old_retained = int(
            diagnostic.z_data[:old_nnz].nbytes
            + diagnostic.z_indices[:old_nnz].nbytes
            + diagnostic.z_indptr[: M6B_W8A_LEGACY_COLUMNS + 1].nbytes
            + diagnostic.r_factor[:M6B_W8A_LEGACY_COLUMNS, :M6B_W8A_LEGACY_COLUMNS].nbytes
        )
        old_work = int(
            _m6b_w8a_w6a_authority(w6a_raw_dir)["summary"]["carrier_audit"]["bounded_work_bytes"]
        )
        audit = diagnostic.audit
        independent_prediction = _m6b_w8a_predicted_live_set(
            old_retained_bytes=old_retained,
            new_retained_bytes=int(audit["retained_z_r_bytes"] + M6B_W6A_MANIFEST_RESERVE_BYTES),
            old_work_bytes=old_work,
            new_work_bytes=int(audit["bounded_work_bytes"]),
        )
        checks["prediction"] = summary.get("prediction") == independent_prediction and independent_prediction["gate"] is True
        checks["store"] = (
            audit.get("columns") == M6B_W8A_COLUMNS
            and audit.get("action_counts") == {"frozen_legacy": 0, "new_base": 140, "selected_repeat": 3, "total": 143}
            and audit.get("retained_z_r_gate") is True
            and audit.get("repeat_exact") is True
            and audit.get("factor_audit", {}).get("rank") == M6B_W8A_COLUMNS
            and audit.get("factor_audit", {}).get("normal_closure") <= M6B_W8A_NORMAL_CLOSURE_LIMIT
        )
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError):
        checks["prediction"] = False
        checks["store"] = False
    finally:
        if diagnostic is not None:
            diagnostic.close()
    jit = summary.get("jit_cache")
    checks["jit"] = _m6b_w6a_jit_cache_valid(jit, __import__("benchmarks.run_task037_extra_h2b", fromlist=["*"]), jit_cache_source, Path(jit.get("target", "")) if isinstance(jit, Mapping) else Path(""))
    checks["fe"] = isinstance(summary.get("fe_audit"), Mapping) and len(summary["fe_audit"].get("z_planes", [])) == 15 and np.allclose(np.asarray(summary["fe_audit"].get("z_planes", []), dtype=float), np.linspace(-10.0, 130.0, 15), rtol=0.0, atol=0.0)
    return {"checks": checks, "pass": all(checks.values()), "summary": summary}


def _run_m6b_w8a_formal_check(
    raw_dir: Path,
    watchdog_summary: Path,
    w6a_raw_dir: Path,
    jit_cache_source: Path,
    output: Path,
    expected_source_sha: str,
) -> int:
    if output.exists():
        raise FileExistsError(f"W8A formal output exists: {output}")
    watchdog = _read_json(watchdog_summary)
    gate = _m6b_w8a_formal_gate(
        raw_dir,
        watchdog,
        Path(watchdog_summary).resolve().parent,
        w6a_raw_dir,
        jit_cache_source,
        expected_source_sha,
    )
    source = __import__("benchmarks.run_task037_extra_h2b", fromlist=["*"])._light_source()
    gate["checks"]["checker_source"] = _m6b_w6a_source_valid(source) and source.get("source_commit_full_sha") == expected_source_sha
    result = {
        "schema": M6B_W8A_FORMAL_CHECK_SCHEMA,
        "status": "pass" if gate["pass"] and gate["checks"]["checker_source"] else "gate_failed",
        "formal_pass": bool(gate["pass"] and gate["checks"]["checker_source"]),
        "pde_pass": False,
        "official_rta": False,
        "w8a_formal_pass": bool(gate["pass"] and gate["checks"]["checker_source"]),
        "checks": gate["checks"],
        "problems": sorted(key for key, passed in gate["checks"].items() if not passed),
        "producer_source_sha": expected_source_sha,
        "checker_source": source,
        "raw_dir": str(Path(raw_dir).resolve()),
        "watchdog_summary": _artifact(Path(watchdog_summary).parent, Path(watchdog_summary).name),
    }
    _write_json(output, _attach_evidence(result))
    return 0 if result["w8a_formal_pass"] else 1


def _m6b_w8a_recovery_progress_valid(path: Path) -> dict[str, Any]:
    try:
        records = [
            json.loads(line)
            for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if len(records) != 154:
            raise ValueError("W8A recovery progress count is invalid")
        if any(
            type(record) is not dict
            or record.get("schema") != f"{M6B_W8A_SCHEMA}.progress.v1"
            or record.get("phase") != M6B_W8A_PHASE
            for record in records
        ):
            raise ValueError("W8A recovery progress identity is invalid")
        fixed = [
            "authority_validated", "mesh_ready", "space_ready", "floquet_mpc_ready",
            "cache_ready", "outer_ready", "legacy_basis_ready", "bubble_spec_ready",
        ]
        if [record["event"] for record in records[:8]] != fixed:
            raise ValueError("W8A recovery fixed progress order is invalid")
        columns = records[8:148]
        if any(
            record.get("event") != "column_progress"
            or record.get("completed") != index
            or record.get("total") != M6B_W8A_ADDED_COLUMNS
            for index, record in enumerate(columns, 1)
        ):
            raise ValueError("W8A recovery column progress is invalid")
        if records[148].get("event") != "bubble_columns_ready" or records[148].get("completed") != M6B_W8A_ADDED_COLUMNS:
            raise ValueError("W8A recovery bubble completion is invalid")
        repeats = records[149:152]
        if any(
            record.get("event") != "repeat_ready"
            or record.get("column_index") != column
            or record.get("completed_repeats") != count
            or record.get("total_repeats") != len(M6B_W8A_REPEAT_COLUMNS)
            for count, (record, column) in enumerate(zip(repeats, M6B_W8A_REPEAT_COLUMNS), 1)
        ):
            raise ValueError("W8A recovery repeat progress is invalid")
        if [record["event"] for record in records[152:]] != ["az_ready", "gram_ready"]:
            raise ValueError("W8A recovery final progress is invalid")
        return {
            "pass": True,
            "record_count": len(records),
            "base_columns": M6B_W8A_ADDED_COLUMNS,
            "repeat_columns": list(M6B_W8A_REPEAT_COLUMNS),
            "last_event": records[-1]["event"],
        }
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        return {"pass": False, "problems": [f"{type(exc).__name__}:{exc}"]}


def _m6b_w8a_recovery_artifacts(raw_dir: Path, watchdog_dir: Path) -> dict[str, Any]:
    inventory: dict[str, dict[str, Any]] = {"raw": {}, "watchdog": {}}
    checks: dict[str, bool] = {}
    for role, root, expected in (
        ("raw", Path(raw_dir), M6B_W8A_RECOVERY_RAW_FILE_SHA256),
        ("watchdog", Path(watchdog_dir), M6B_W8A_RECOVERY_WATCHDOG_FILE_SHA256),
    ):
        role_ok = True
        for name, sha256 in expected.items():
            actual = _artifact(root, name)
            inventory[role][name] = actual
            role_ok = role_ok and actual.get("present") is True and actual.get("sha256") == sha256
        checks[role] = role_ok
    return {"pass": all(checks.values()), "checks": checks, "inventory": inventory}


def _m6b_w8a_recovery_gate(
    raw_dir: Path,
    watchdog_dir: Path,
    w6a_raw_dir: Path,
    jit_cache_source: Path,
    expected_producer_sha: str,
    companion_summary_path: Path | None,
    companion_watchdog_path: Path | None,
    expected_companion_source_sha: str | None,
) -> dict[str, Any]:
    import numpy as np
    from src.solvers.hcurl_m6b_w8a_z_bubble_range import (
        W8A_SCHEMA as CORE_SCHEMA,
        fixed_w8a_column_specs,
        validate_w8a_store,
    )

    raw_dir = Path(raw_dir).resolve()
    watchdog_dir = Path(watchdog_dir).resolve()
    w6a_raw_dir = Path(w6a_raw_dir).resolve()
    jit_cache_source = Path(jit_cache_source).resolve()
    checks: dict[str, bool] = {
        "producer_sha": expected_producer_sha == M6B_W8A_RECOVERY_PRODUCER_SHA,
        "paths": raw_dir == (ROOT / M6B_W8A_RECOVERY_RAW_RELATIVE_PATH).resolve()
        and watchdog_dir == Path(M6B_W8A_RECOVERY_WATCHDOG_PATH).resolve(),
    }
    artifacts = _m6b_w8a_recovery_artifacts(raw_dir, watchdog_dir)
    checks["artifact_hashes"] = artifacts["pass"]
    watchdog: Mapping[str, Any] = {}
    stdout = ""
    try:
        value = _read_json(watchdog_dir / "w8a_watchdog_summary.json")
        if isinstance(value, Mapping):
            watchdog = value
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError):
        pass
    try:
        stdout = (watchdog_dir / "w8a_z_bubble_range_builder_stdout.txt").read_text(encoding="utf-8")
    except OSError:
        pass
    independent_timeline = _m6b_w8a_timeline_valid(
        watchdog_dir / "w8a_z_bubble_range_builder_timeline.jsonl"
    )
    process = watchdog.get("process")
    drain = watchdog.get("drain")
    source_start = watchdog.get("source_at_start")
    source_end = watchdog.get("source_at_end")
    checks["source"] = bool(
        _m6b_w6a_source_valid(source_start)
        and _m6b_w6a_source_valid(source_end)
        and source_start.get("source_commit_full_sha") == M6B_W8A_RECOVERY_PRODUCER_SHA
        and source_end.get("source_commit_full_sha") == M6B_W8A_RECOVERY_PRODUCER_SHA
        and watchdog.get("source_end_clean") is True
    )
    checks["old_watchdog"] = bool(
        _evidence_valid(watchdog)
        and watchdog.get("schema") == M6B_W8A_WATCHDOG_SCHEMA
        and watchdog.get("phase") == M6B_W8A_PHASE
        and watchdog.get("status") == "gate_failed"
        and watchdog.get("process", {}).get("return_code") == 1
        and watchdog.get("process", {}).get("termination") is None
        and watchdog.get("drain", {}).get("gone") is True
        and watchdog.get("timeline") == independent_timeline
    )
    checks["resource"] = bool(
        isinstance(process, Mapping)
        and process.get("peak_rss_bytes", 0) < M6B_W8A_BUILDER_RSS_LIMIT_BYTES
        and process.get("swap_bytes") == 0
        and isinstance(drain, Mapping)
        and drain.get("gone") is True
        and independent_timeline.get("pass") is True
        and independent_timeline.get("peak_rss_bytes") == process.get("peak_rss_bytes")
        and independent_timeline.get("swap_bytes") == 0
        and independent_timeline.get("compiler_descendant_pids") == []
    )
    progress = _m6b_w8a_recovery_progress_valid(raw_dir / "w8a_progress.jsonl")
    checks["progress"] = progress["pass"] is True
    checks["failure_boundary"] = bool(
        '"event": "gram_ready"' in stdout
        and "NameError: name '_jsonable' is not defined" in stdout
        and '"event": "summary_ready"' not in stdout
        and stdout.index('"event": "gram_ready"') < stdout.index("NameError: name '_jsonable' is not defined")
    )
    w6a_authority: dict[str, Any] = {}
    try:
        w6a_authority = _m6b_w8a_w6a_authority(w6a_raw_dir)
        p6_identity = w6a_authority["summary"].get("p6_identity")
        checks["w6a_authority"] = p6_identity == {
            "global_cells": M6B_GLOBAL_CELLS,
            "local_cells": M6B_GLOBAL_CELLS,
            "local_nloc": M6B_LOCAL_NLOC,
            "global_rows": M6B_GLOBAL_ROWS,
            "constraint_count": M6B_CONSTRAINTS,
        }
        _m6b_w8a_legacy_store_dir(w6a_raw_dir)
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError):
        checks["w6a_authority"] = False
    jit_inventory: dict[str, Any] = {}
    try:
        h2b = __import__("benchmarks.run_task037_extra_h2b", fromlist=["*"])
        jit_inventory = _m6b_w6a_cache_record(h2b, jit_cache_source)
        checks["jit"] = (
            jit_cache_source == (
                ROOT
                / "benchmarks/artifacts/task037_extra_development/"
                "m6b_w1a_e2f99a3_builder_run1/jit_cache"
            ).resolve()
            and jit_inventory.get("inventory_sha256") == M6B_W8A_W6A_JIT_INVENTORY_SHA256
        )
    except (OSError, TypeError, ValueError, KeyError):
        checks["jit"] = False
    manifest: Mapping[str, Any] = {}
    store_validation: dict[str, Any] = {"pass": False}
    prediction: dict[str, Any] = {}
    retained_z_r_bytes = None
    try:
        manifest_value = _read_json(raw_dir / "sparse_range_store/manifest.json")
        if isinstance(manifest_value, Mapping):
            manifest = manifest_value
        fixed_identity = manifest.get("identity")
        w6a_summary = w6a_authority.get("summary", {})
        old_store_manifest = w6a_summary.get("store_manifest_artifact")
        old_carrier = w6a_summary.get("carrier_audit")
        checks["fixed_identity"] = bool(
            manifest.get("schema") == CORE_SCHEMA
            and manifest.get("columns") == M6B_W8A_COLUMNS
            and manifest.get("global_rows") == M6B_GLOBAL_ROWS
            and manifest.get("ownership_range") == [0, M6B_GLOBAL_ROWS]
            and manifest.get("column_specs") == [spec.__dict__ for spec in fixed_w8a_column_specs()]
            and manifest.get("action_counts") == {"frozen_legacy": 0, "new_base": 140, "selected_repeat": 3, "total": 143}
            and manifest.get("repeat_columns") == list(M6B_W8A_REPEAT_COLUMNS)
            and manifest.get("repeat_exact") is True
            and manifest.get("dense_z_retained") is False
            and manifest.get("dense_az_retained") is False
            and manifest.get("az_builder_only") is True
            and manifest.get("az_production_retained") is False
            and isinstance(fixed_identity, Mapping)
            and fixed_identity.get("source_sha") == M6B_W8A_RECOVERY_PRODUCER_SHA
            and fixed_identity.get("fine_space") == "uncondensed_fullspace"
            and fixed_identity.get("global_matrix") is False
            and fixed_identity.get("static_condensation") is False
            and fixed_identity.get("trace_slab_pc") is False
            and fixed_identity.get("dtn_matrix_free") is True
            and isinstance(old_store_manifest, Mapping)
            and fixed_identity.get("legacy_w6a_manifest_sha256") == old_store_manifest.get("sha256")
            and isinstance(old_carrier, Mapping)
            and fixed_identity.get("legacy_w6a_az_column_sha256_aggregate") == old_carrier.get("az_column_sha256_aggregate")
        )
        store_validation = validate_w8a_store(
            raw_dir / "sparse_range_store/manifest.json",
            legacy_store_dir=_m6b_w8a_legacy_store_dir(w6a_raw_dir),
        )
        checks["store"] = bool(
            store_validation.get("pass") is True
            and store_validation.get("rank") == M6B_W8A_COLUMNS
            and store_validation.get("normal_closure", float("inf")) <= M6B_W8A_NORMAL_CLOSURE_LIMIT
            and store_validation.get("gram_hermitian_defect", float("inf")) <= M6B_W8A_NORMAL_CLOSURE_LIMIT
        )
        arrays = manifest["arrays"]
        retained_z_r_bytes = int(
            sum(int(arrays[name]["nbytes"]) for name in ("z_data", "z_indices", "z_indptr", "r_factor"))
        )
        old_retained = int(w6a_summary["carrier_audit"]["retained_z_r_bytes"])
        old_work = int(w6a_summary["carrier_audit"]["bounded_work_bytes"])
        new_work = int(5 * M6B_GLOBAL_ROWS * 16)
        prediction = _m6b_w8a_predicted_live_set(
            old_retained_bytes=old_retained,
            new_retained_bytes=retained_z_r_bytes + M6B_W6A_MANIFEST_RESERVE_BYTES,
            old_work_bytes=old_work,
            new_work_bytes=new_work,
        )
        checks["retained_payload"] = retained_z_r_bytes <= M6B_W8A_RETAINED_LIMIT_BYTES
        checks["prediction"] = prediction["gate"] is True
    except (OSError, TypeError, ValueError, KeyError, IndexError, json.JSONDecodeError):
        checks["fixed_identity"] = False
        checks["store"] = False
        checks["retained_payload"] = False
        checks["prediction"] = False
    source_delta = {"pass": False, "reason": "companion source is missing"}
    companion = {
        "pass": False,
        "checks": {"present": False},
    }
    if (
        companion_summary_path is not None
        and companion_watchdog_path is not None
        and isinstance(expected_companion_source_sha, str)
    ):
        try:
            companion = _m6b_w8a_companion_gate(
                companion_summary_path,
                companion_watchdog_path,
                w6a_raw_dir,
                jit_cache_source,
                expected_companion_source_sha,
            )
        except (OSError, TypeError, ValueError, KeyError, IndexError, json.JSONDecodeError):
            companion = {"pass": False, "checks": {"exception": False}}
        source_delta = _m6b_w8a_recovery_source_delta(expected_companion_source_sha)
    checks["companion"] = companion.get("pass") is True
    checks["source_delta"] = source_delta.get("pass") is True
    unavailable = ["builder_summary", "action_audit", "fe_audit", "runtime_identity"]
    recoverable_pass = all(checks.values())
    recovered_numeric_gate_pass = bool(
        checks.get("fixed_identity")
        and checks.get("store")
        and checks.get("retained_payload")
        and checks.get("prediction")
    )
    return {
        "checks": checks,
        "recoverable_pass": recoverable_pass,
        "recovered_numeric_gate_pass": recovered_numeric_gate_pass,
        "qualified_for_w8b": bool(recoverable_pass and recovered_numeric_gate_pass),
        "progress": progress,
        "timeline": independent_timeline,
        "watchdog": watchdog,
        "artifacts": artifacts,
        "store_validation": store_validation,
        "manifest": manifest,
        "prediction": prediction,
        "retained_z_r_bytes": retained_z_r_bytes,
        "jit_inventory": jit_inventory,
        "unavailable": unavailable,
        "producer_measurement": {
            "source_sha": M6B_W8A_RECOVERY_PRODUCER_SHA,
            "raw_dir": str(raw_dir),
            "watchdog_dir": str(watchdog_dir),
            "watchdog_status": watchdog.get("status"),
            "artifact_hashes": checks["artifact_hashes"],
            "old_watchdog": checks["old_watchdog"],
            "resource": checks["resource"],
            "failure_boundary": checks["failure_boundary"],
            "progress": progress,
            "store_validation": store_validation,
        },
        "companion_verification": companion,
        "source_delta": source_delta,
    }


def _run_m6b_w8a_recovery(
    raw_dir: Path,
    watchdog_dir: Path,
    w6a_raw_dir: Path,
    jit_cache_source: Path,
    output: Path,
    expected_producer_sha: str,
    companion_summary_path: Path,
    companion_watchdog_path: Path,
    expected_companion_source_sha: str,
) -> int:
    if output.exists():
        raise FileExistsError(f"W8A recovery output exists: {output}")
    raw_dir = Path(raw_dir).resolve()
    watchdog_dir = Path(watchdog_dir).resolve()
    output = Path(output).resolve()
    if output == raw_dir or output == watchdog_dir or output.is_relative_to(raw_dir) or output.is_relative_to(watchdog_dir):
        raise ValueError("W8A recovery output must be outside frozen evidence")
    gate = _m6b_w8a_recovery_gate(
        raw_dir,
        watchdog_dir,
        w6a_raw_dir,
        jit_cache_source,
        expected_producer_sha,
        companion_summary_path,
        companion_watchdog_path,
        expected_companion_source_sha,
    )
    h2b = __import__("benchmarks.run_task037_extra_h2b", fromlist=["*"])
    checker_source = h2b._light_source()
    checker_source_ok = bool(
        _m6b_w6a_source_valid(checker_source)
        and checker_source.get("source_commit_full_sha") == expected_companion_source_sha
    )
    gate["checks"]["recovery_checker_source"] = checker_source_ok
    recoverable_pass = bool(gate["recoverable_pass"] and checker_source_ok)
    qualified = bool(gate["qualified_for_w8b"] and checker_source_ok)
    result = {
        "schema": M6B_W8A_RECOVERY_SCHEMA,
        "phase": M6B_W8A_RECOVERY_PHASE,
        "status": "recovery_complete" if recoverable_pass else "gate_failed",
        "classification": (
            "RECOVERED_QUALIFIED_FOR_W8B"
            if qualified
            else "RECOVERED_NUMERIC_NOT_W8B"
            if gate["recovered_numeric_gate_pass"]
            else "RECOVERY_GATE_FAILED"
        ),
        "formal_pass": False,
        "pde_pass": False,
        "official_rta": False,
        "original_builder_execution_pass": False,
        "old_watchdog_status": gate["watchdog"].get("status"),
        "recovered_numeric_gate_pass": gate["recovered_numeric_gate_pass"],
        "qualified_for_w8b": qualified,
        "producer_source_sha": M6B_W8A_RECOVERY_PRODUCER_SHA,
        "companion_source_sha": expected_companion_source_sha,
        "raw_dir": str(raw_dir),
        "watchdog_dir": str(watchdog_dir),
        "recovery_checker_source": checker_source,
        "checks": gate["checks"],
        "problems": sorted(key for key, passed in gate["checks"].items() if not passed),
        "unavailable": gate["unavailable"],
        "progress": gate["progress"],
        "timeline": gate["timeline"],
        "artifact_inventory": gate["artifacts"]["inventory"],
        "watchdog_process": gate["watchdog"].get("process"),
        "store_validation": gate["store_validation"],
        "retained_z_r_bytes": gate["retained_z_r_bytes"],
        "prediction": gate["prediction"],
        "jit_inventory": gate["jit_inventory"],
        "producer_measurement": gate["producer_measurement"],
        "companion_verification": gate["companion_verification"],
        "companion_gate_pass": gate["companion_verification"].get("pass") is True,
        "source_delta": gate["source_delta"],
        "recovery_semantics": {
            "action_audit": "unavailable_not_reconstructed",
            "fe_audit": "unavailable_not_reconstructed",
            "runtime_identity": "unavailable_not_reconstructed",
            "source_of_numeric_evidence": "immutable_manifest_progress_store_watchdog",
        },
    }
    _write_json(output, _attach_evidence(result))
    return 0 if qualified else 1


def _m6b_w8a_action_audit_valid(
    value: Any,
    *,
    expected_frozen_legacy: int = 0,
    expected_new_base: int = M6B_W8A_ADDED_COLUMNS,
    expected_repeat: int = len(M6B_W8A_REPEAT_COLUMNS),
    expected_total: int = M6B_W8A_ADDED_COLUMNS + len(M6B_W8A_REPEAT_COLUMNS),
) -> bool:
    if not isinstance(value, Mapping):
        return False
    bridge = value.get("bridge")
    outer = value.get("outer_context")
    physical = value.get("physical_action")
    dtn = value.get("dtn_action")
    return bool(
        value.get("frozen_legacy_action_count") == expected_frozen_legacy
        and value.get("new_base_action_count") == expected_new_base
        and value.get("selected_repeat_action_count") == expected_repeat
        and value.get("total_new_action_count") == expected_total
        and value.get("outer_forward_apply_count") == expected_total
        and isinstance(bridge, Mapping)
        and bridge.get("fixed_work_vectors") == 2
        and bridge.get("vector_create_count") == 2
        and bridge.get("per_apply_vec_creation") == 0
        and bridge.get("forward_apply_count") == expected_total
        and isinstance(outer, Mapping)
        and outer.get("apply_count") == expected_total
        and outer.get("matrix_type") == "python_action_only"
        and outer.get("global_matrix") is False
        and outer.get("augmented_matrix") is False
        and outer.get("static_condensation") is False
        and outer.get("trace_slab") is False
        and outer.get("explicit_C_materialized_count") == 0
        and outer.get("explicit_D_materialized_count") == 0
        and isinstance(physical, Mapping)
        and physical.get("apply_count") == expected_total
        and physical.get("global_matrix_materialized") is False
        and physical.get("global_constraint_matrix_materialized") is False
        and physical.get("global_condensed_schur_materialized") is False
        and physical.get("cell_schur_matrix_materialized") is False
        and physical.get("slab_matrix_materialized") is False
        and physical.get("retained_dense_cell_tensor_count") == 0
        and physical.get("dense_cell_tensor_materialized_per_apply") is False
        and physical.get("factor_count") == 0
        and physical.get("ksp_created") is False
        and physical.get("cell_schur_matrix_nnz") == 0
        and physical.get("slab_matrix_nnz") == 0
        and physical.get("explicit_C_materialized_count") == 0
        and physical.get("explicit_D_materialized_count") == 0
        and physical.get("ordinary_default_changed") is False
        and isinstance(dtn, Mapping)
        and dtn.get("apply_count") == expected_total
        and dtn.get("mode_count") == 80
        and dtn.get("fine_space") == "uncondensed_fullspace"
        and dtn.get("condensation") is False
        and dtn.get("static_condensed_operator_used") is False
        and dtn.get("trace_slab_pc_used") is False
        and dtn.get("global_matrix_materialized") is False
        and dtn.get("augmented_matrix_materialized") is False
        and dtn.get("explicit_C_materialized_count") == 0
        and dtn.get("explicit_D_materialized_count") == 0
        and dtn.get("fe_sized_allgather") is False
        and dtn.get("modal_allreduce_count_per_apply") == 1
        and dtn.get("modal_allreduce_count_per_hermitian_apply") == 1
    )


def _m6b_w8a_artifact_inventory_valid(
    inventory: Any, raw_dir: Path, watchdog_dir: Path
) -> bool:
    if not isinstance(inventory, Mapping):
        return False
    expected = {
        "raw": {
            "w8a_summary.json",
            "w8a_progress.jsonl",
            "sparse_range_store/manifest.json",
            "sparse_range_store/z_data.npy",
            "sparse_range_store/z_indices.npy",
            "sparse_range_store/z_indptr.npy",
            "sparse_range_store/gram.npy",
            "sparse_range_store/r_factor.npy",
        },
        "watchdog": {
            f"{M6B_W8A_PHASE}_timeline.jsonl",
            f"{M6B_W8A_PHASE}_stdout.txt",
            f"{M6B_W8A_PHASE}_root_pid.json",
        },
    }
    roots = {"raw": Path(raw_dir), "watchdog": Path(watchdog_dir)}
    for role in ("raw", "watchdog"):
        records = inventory.get(role)
        if not isinstance(records, list) or {
            item.get("path") for item in records if isinstance(item, Mapping)
        } != expected[role]:
            return False
        for name in expected[role]:
            reported = next(
                (item for item in records if isinstance(item, Mapping) and item.get("path") == name),
                None,
            )
            actual = _artifact(roots[role], name)
            if (
                reported != actual
                or actual.get("present") is not True
                or type(actual.get("bytes")) is not int
                or actual["bytes"] <= 0
                or not _m6b_w6a_valid_sha(actual.get("sha256"))
            ):
                return False
    return True


def _m6b_w8b_load_residual(raw_dir: Path, record: Mapping[str, Any], *, array_hash: Callable[[Any], str]) -> np.ndarray:
    import numpy as np

    name = record.get("path")
    if not isinstance(name, str) or Path(name).name != name:
        raise ValueError("W8B residual path is invalid")
    actual = _artifact(Path(raw_dir), name)
    values = np.load(Path(raw_dir) / name, allow_pickle=False, mmap_mode="r")
    if actual.get("sha256") != record.get("sha256") or values.dtype != np.dtype(np.complex128) or values.shape != (M6B_GLOBAL_ROWS,) or not np.all(np.isfinite(values)) or array_hash(values) != record.get("array_sha256"):
        raise ValueError("W8B residual authority differs")
    return values


def _m6b_w9a_load_array(raw_dir: Path, record: Mapping[str, Any], name: str) -> tuple[Any, dict[str, Any]]:
    import numpy as np

    if not isinstance(record, Mapping) or record.get("path") != name:
        raise ValueError(f"W9A artifact path is invalid: {name}")
    actual = _artifact(Path(raw_dir), name)
    values = np.load(Path(raw_dir) / name, allow_pickle=False, mmap_mode="r")
    if not (
        actual.get("present") is True
        and type(actual.get("bytes")) is int
        and record.get("bytes") == actual["bytes"]
        and record.get("sha256") == actual.get("sha256")
        and values.dtype == np.dtype(np.complex128)
        and values.shape == (M6B_GLOBAL_ROWS,)
        and np.all(np.isfinite(values))
        and record.get("array_sha256") == _m6b_w6a_w5_legacy_raw_array_sha256(values)
    ):
        raise ValueError(f"W9A artifact differs: {name}")
    return values, {
        "path": name,
        "bytes": actual["bytes"],
        "file_sha256": actual["sha256"],
        "array_sha256": record["array_sha256"],
    }


def _m6b_w9a_load_w5(compact_path: Path, raw_dir: Path) -> dict[str, Any]:
    authority = _m6b_w6a_w5_compact_authority()
    compact_path = Path(compact_path).resolve()
    if compact_path != Path(authority["path"]).resolve():
        raise ValueError("W9A W5 compact path is not the frozen authority")
    samples = authority["record"].get("screen", {}).get("samples")
    if not isinstance(samples, Mapping) or set(samples) != {str(i) for i in M6B_W9A_CHECKPOINTS}:
        raise ValueError("W9A W5 checkpoint authority is incomplete")
    checkpoints: dict[int, dict[str, Any]] = {}
    artifacts: dict[str, Any] = {}
    for iteration in M6B_W9A_CHECKPOINTS:
        item = samples[str(iteration)]
        records = item.get("artifacts") if isinstance(item, Mapping) else None
        if not isinstance(records, Mapping):
            raise ValueError(f"W9A W5 artifacts are missing: {iteration}")
        checkpoints[iteration] = {}
        artifacts[str(iteration)] = {}
        for name in ("solution", "outer_action"):
            file_name = f"m6b_iter{iteration}_{name}.npy"
            values, artifact = _m6b_w9a_load_array(raw_dir, records.get(name), file_name)
            checkpoints[iteration][name] = values
            artifacts[str(iteration)][name] = artifact
    records_200 = samples["200"].get("artifacts")
    residual, residual_artifact = _m6b_w9a_load_array(
        raw_dir, records_200.get("residual"), "m6b_iter200_residual.npy"
    )
    return {
        "compact": {"path": authority["path"], "file_sha256": authority["file_sha256"], "producer_source_sha": M6B_W6A_W5_SOURCE_SHA},
        "raw_dir": str(Path(raw_dir).resolve()),
        "checkpoints": checkpoints,
        "artifacts": artifacts,
        "residual": residual,
        "residual_artifact": residual_artifact,
    }


def _m6b_w9a_load_w7(compact_path: Path, raw_dir: Path) -> dict[str, Any]:
    authority = _m6b_w8a_w7_compact_authority(compact_path)
    sample = authority["sample"]
    if sample.get("cumulative_iteration") != 400:
        raise ValueError("W9A W7 cumulative-400 authority is missing")
    records = sample.get("artifacts")
    if not isinstance(records, Mapping):
        raise ValueError("W9A W7 residual authority is missing")
    record = records.get("residual")
    if not isinstance(record, Mapping) or not isinstance(record.get("path"), str):
        raise ValueError("W9A W7 residual authority is incomplete")
    residual, artifact = _m6b_w9a_load_array(raw_dir, record, record["path"])
    return {
        "compact": {
            "path": str(compact_path),
            "file_sha256": authority["artifact"]["sha256"],
            "producer_source_sha": M6B_W8A_W7_SOURCE_SHA,
        },
        "raw_dir": str(Path(raw_dir).resolve()),
        "residual": residual,
        "residual_artifact": artifact,
        "cumulative_iteration": 400,
    }


def _m6b_w9a_result(value: Mapping[str, Any], *, role: str, residual_hash: str, repeat: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    result["singular_values"] = [float(item) for item in value["singular_values"]]
    coefficients = value["coefficients"]
    result["coefficients"] = None if coefficients is None else [[float(item.real), float(item.imag)] for item in coefficients]
    result.update({"role": role, "residual_array_sha256": residual_hash, "repeat_exact": bool(repeat["repeat_exact"])})
    return result


def _m6b_w9a_measurement(recycle: Any, delta_action: Any, residual: Any, *, role: str, residual_hash: str) -> dict[str, Any]:
    import numpy as np

    first = recycle.project_residual(delta_action, residual)
    second = recycle.project_residual(delta_action, residual)
    repeat = {
        "repeat_exact": bool(
            np.array_equal(first["singular_values"], second["singular_values"])
            and np.array_equal(first["coefficients"], second["coefficients"])
            and first["rho"] == second["rho"]
            and first["normal_closure"] == second["normal_closure"]
        )
    }
    return _m6b_w9a_result(first, role=role, residual_hash=residual_hash, repeat=repeat)


def _m6b_w9a_numeric_gate(measurements: Any) -> dict[str, Any]:
    required = {"control_w5_iter200", "target_w7_cumulative400"}
    checks = {"measurement_set": False, "rank": False, "finite_deterministic": False, "projection_closure": False, "control_sanity": False, "target_rho": False}
    problems: list[str] = []
    if not isinstance(measurements, Mapping) or set(measurements) != required:
        problems.append("measurement_set")
        return {"checks": checks, "pass": False, "problems": problems}
    if not all(isinstance(measurements[label], Mapping) for label in required):
        checks["measurement_set"] = False
        return {"checks": checks, "pass": False, "problems": ["measurement_type"]}
    checks["measurement_set"] = True
    values = [measurements[label] for label in sorted(required)]
    checks["rank"] = all(item.get("rank") == 4 and item.get("column_count") == 4 for item in values)
    checks["finite_deterministic"] = all(item.get("finite") is True and item.get("repeat_exact") is True and _finite_number(item.get("rho")) for item in values)
    checks["projection_closure"] = all(_finite_number(item.get("normal_closure")) and item["normal_closure"] <= M6B_W9A_NORMAL_CLOSURE_LIMIT for item in values)
    control = measurements["control_w5_iter200"]
    target = measurements["target_w7_cumulative400"]
    checks["control_sanity"] = bool(
        _finite_number(control.get("rho"))
        and M6B_W9A_CONTROL_RHO_LOWER <= control["rho"] <= M6B_W9A_CONTROL_RHO_UPPER
        and _finite_number(control.get("captured_energy_ratio"))
        and control["captured_energy_ratio"] <= M6B_W9A_CONTROL_CAPTURED_ENERGY_LIMIT
    )
    checks["target_rho"] = _finite_number(target.get("rho")) and target["rho"] <= M6B_W9A_TARGET_RHO_LIMIT
    for name, passed in checks.items():
        if not passed:
            problems.append(name)
    return {"checks": checks, "pass": all(checks.values()), "problems": sorted(set(problems))}


def _run_m6b_w9a_check(
    w5_raw_dir: Path,
    w5_compact: Path,
    w7_raw_dir: Path,
    w7_compact: Path,
    output: Path,
    expected_source_sha: str,
) -> int:
    import time

    if output.exists():
        raise FileExistsError(f"W9A output exists: {output}")
    started = time.perf_counter()
    h2b = __import__("benchmarks.run_task037_extra_h2b", fromlist=["*"])
    source_start = h2b._light_source()
    if not (_m6b_w6a_source_valid(source_start) and source_start.get("source_commit_full_sha") == expected_source_sha):
        raise RuntimeError("W9A checker source is not clean or expected")
    w5 = _m6b_w9a_load_w5(w5_compact, w5_raw_dir)
    w7 = _m6b_w9a_load_w7(w7_compact, w7_raw_dir)
    recycle = __import__("src.solvers.checkpoint_recycle", fromlist=["*"])
    increments = recycle.build_checkpoint_increments(w5["checkpoints"])
    control = _m6b_w9a_measurement(recycle, increments["dAX"], w5["residual"], role="control_w5_iter200", residual_hash=w5["residual_artifact"]["array_sha256"])
    target = _m6b_w9a_measurement(recycle, increments["dAX"], w7["residual"], role="target_w7_cumulative400", residual_hash=w7["residual_artifact"]["array_sha256"])
    measurements = {"control_w5_iter200": control, "target_w7_cumulative400": target}
    numeric_gate = _m6b_w9a_numeric_gate(measurements)
    source_end = h2b._light_source()
    source_ok = _m6b_w6a_source_valid(source_end) and source_end.get("source_commit_full_sha") == expected_source_sha
    checks = dict(numeric_gate["checks"])
    checks["source"] = source_ok
    passed = bool(numeric_gate["pass"] and source_ok)
    result = {
        "schema": M6B_W9A_CHECK_SCHEMA,
        "phase": M6B_W9A_PHASE,
        "status": "diagnostic_complete" if passed else "gate_failed",
        "classification": "W9A_QUALIFIED" if passed else "W9A_NUMERIC_OR_AUTHORITY_FAIL",
        "diagnostic_only": True,
        "w9a_pass": passed,
        "formal_pass": False,
        "pde_pass": False,
        "official_rta": False,
        "expected_source_sha": expected_source_sha,
        "source_at_start": source_start,
        "source_at_end": source_end,
        "authorities": {"w5": w5["compact"], "w7": w7["compact"], "w5_raw_dir": w5["raw_dir"], "w7_raw_dir": w7["raw_dir"]},
        "checkpoint_artifacts": w5["artifacts"],
        "w5_residual_artifact": w5["residual_artifact"],
        "w7_residual_artifact": w7["residual_artifact"],
        "increment_identity": {"checkpoint_iterations": list(increments["checkpoint_iterations"]), "dX_array_sha256": _m6b_w2_array_sha256(increments["dX"]), "dAX_array_sha256": _m6b_w2_array_sha256(increments["dAX"])},
        "measurements": measurements,
        "numeric_gate": numeric_gate,
        "limits": {
            "target_rho": M6B_W9A_TARGET_RHO_LIMIT,
            "control_rho": [M6B_W9A_CONTROL_RHO_LOWER, M6B_W9A_CONTROL_RHO_UPPER],
            "control_captured_energy_ratio": M6B_W9A_CONTROL_CAPTURED_ENERGY_LIMIT,
            "normal_closure": M6B_W9A_NORMAL_CLOSURE_LIMIT,
        },
        "checks": checks,
        "pass": passed,
        "problems": sorted(set(numeric_gate["problems"] + ([] if source_ok else ["source"]))),
        "scope": {"algorithm": "fixed four-checkpoint recycle projection", "checkpoint_axis": "20/100/150/200", "action_calls": 0, "pde_calls": 0, "scalable_pc": False},
        "elapsed_seconds": time.perf_counter() - started,
    }
    _write_json(output, _attach_evidence(result))
    return 0 if passed else 1


def _m6b_w10a_basis_authority(w5_raw_dir: Path, compact_record: Mapping[str, Any]) -> dict[str, Any]:
    basis = (Path(w5_raw_dir).resolve() / M6B_W10A_BASIS_RELATIVE_PATH).resolve()
    core = compact_record.get("screen", {}).get("core_audit") if isinstance(compact_record, Mapping) else None
    basis_audit = core.get("v_basis") if isinstance(core, Mapping) else None
    required = {
        "rows": M6B_GLOBAL_ROWS,
        "capacity": M6B_W10A_COLUMNS,
        "written_count": M6B_W10A_COLUMNS,
        "allocated_bytes": M6B_W10A_BASIS_BYTES,
        "dtype": "complex128",
        "path": str(basis),
    }
    if not isinstance(basis_audit, Mapping) or any(basis_audit.get(key) != value for key, value in required.items()):
        raise ValueError("W10A compact v_basis audit is not closed")
    artifact = _artifact(Path(w5_raw_dir).resolve(), M6B_W10A_BASIS_RELATIVE_PATH)
    if artifact.get("present") is not True or artifact.get("bytes") != M6B_W10A_BASIS_BYTES:
        raise ValueError("W10A v_basis scratch file differs")
    stat = basis.stat()
    return {
        "path": str(basis),
        "bytes": int(stat.st_size),
        "sha256": artifact["sha256"],
        "mode": stat.st_mode,
        "mtime_ns": stat.st_mtime_ns,
        "current_scratch_hash_bound": True,
        "historical_producer_hash_available": False,
        "compact_core_audit": dict(basis_audit),
    }


def _m6b_w10a_measurement_record(
    core_measurement: Mapping[str, Any],
    q_overlap_energy: float,
    span: Any,
    *,
    allow_actionable: bool = True,
) -> dict[str, Any]:
    import numpy as np

    scalar_keys = (
        "normal_closure",
        "captured_energy",
        "captured_energy_ratio",
        "captured_energy_ratio_raw",
        "rho_full",
        "coefficient_norm",
    )
    result = {
        key: float(core_measurement[key]) if _finite_number(core_measurement.get(key)) else None
        for key in scalar_keys
    }
    result["available"] = True
    result["finite"] = core_measurement["finite"] is True
    result["q_overlap_energy_ratio"] = float(q_overlap_energy)
    result["actionable_available"] = bool(allow_actionable)
    if allow_actionable:
        actionable = span.add_actionable_projection(core_measurement, q_overlap_energy)
        result["captured_actionable_energy_ratio"] = float(actionable["captured_actionable_energy_ratio"])
        result["rho_optimistic"] = float(actionable["rho_optimistic"])
    result["finite"] = bool(
        result["finite"]
        and all(result[key] is not None for key in scalar_keys)
        and np.isfinite(result["q_overlap_energy_ratio"])
        and (
            not allow_actionable
            or (
                np.isfinite(result["captured_actionable_energy_ratio"])
                and np.isfinite(result["rho_optimistic"])
            )
        )
    )
    return result


def _m6b_w10a_ratio_valid(value: Any) -> bool:
    return _finite_number(value) and -1.0e-11 <= float(value) <= 1.0 + 1.0e-11


def _m6b_w10a_unavailable_measurement(problem: str) -> dict[str, Any]:
    return {
        "available": False,
        "actionable_available": False,
        "finite": False,
        "problems": [problem],
    }


def _m6b_w10a_numeric_gate(analysis: Mapping[str, Any], measurements: Mapping[str, Any], repeat_exact: bool) -> dict[str, Any]:
    checks = {
        "rank": analysis.get("rank") == M6B_W10A_COLUMNS,
        "gram_hermitian": _finite_number(analysis.get("gram_hermitian_defect")) and analysis["gram_hermitian_defect"] <= 1.0e-11,
        "gram_eigenvalues": bool(
            analysis.get("gram_valid") is True
            and _finite_number(analysis.get("eig_min"))
            and _finite_number(analysis.get("eig_max"))
            and _finite_number(analysis.get("negative_eigenvalue_limit"))
            and analysis["eig_min"] >= -analysis["negative_eigenvalue_limit"]
        ),
        "finite_deterministic": analysis.get("finite") is True and repeat_exact,
        "measurement_set": isinstance(measurements, Mapping) and set(measurements) == {"control_w5_iter200", "target_w7_cumulative400"},
        "captured_ratios": False,
        "projection_closure": False,
        "r5_in_span": False,
        "control_sanity": False,
        "target_rho": False,
    }
    if checks["measurement_set"]:
        control = measurements["control_w5_iter200"]
        target = measurements["target_w7_cumulative400"]
        values = (control, target)
        checks["captured_ratios"] = all(
            isinstance(item, Mapping)
            and _m6b_w10a_ratio_valid(item.get("captured_energy_ratio"))
            and _m6b_w10a_ratio_valid(item.get("captured_actionable_energy_ratio"))
            for item in values
        )
        checks["projection_closure"] = all(
            isinstance(item, Mapping)
            and item.get("finite") is True
            and _finite_number(item.get("normal_closure"))
            and item["normal_closure"] <= 1.0e-11
            for item in values
        )
        checks["r5_in_span"] = _finite_number(control.get("rho_full")) and control["rho_full"] <= 1.0e-10
        checks["control_sanity"] = _finite_number(control.get("rho_optimistic")) and control["rho_optimistic"] >= M6B_W10A_CONTROL_RHO_LOWER
        checks["target_rho"] = _finite_number(target.get("rho_optimistic")) and target["rho_optimistic"] <= M6B_W10A_TARGET_RHO_LIMIT
    problems = sorted(name for name, passed in checks.items() if not passed)
    return {"checks": checks, "pass": not problems, "problems": problems}


def _run_m6b_w10a_check(
    w5_raw_dir: Path,
    w5_compact: Path,
    w7_raw_dir: Path,
    w7_compact: Path,
    output: Path,
    expected_source_sha: str,
) -> int:
    import time
    import numpy as np

    if output.exists():
        raise FileExistsError(f"W10A output exists: {output}")
    started = time.perf_counter()
    h2b = __import__("benchmarks.run_task037_extra_h2b", fromlist=["*"])
    source_start = h2b._light_source()
    if not (_m6b_w6a_source_valid(source_start) and source_start.get("source_commit_full_sha") == expected_source_sha):
        raise RuntimeError("W10A checker source is not clean or expected")
    w5_authority = _m6b_w6a_w5_compact_authority()
    if Path(w5_compact).resolve() != Path(w5_authority["path"]).resolve():
        raise ValueError("W10A W5 compact path is not the frozen authority")
    w5 = _m6b_w7_s1_load_w5_authority(w5_compact, w5_raw_dir)
    basis = _m6b_w10a_basis_authority(w5_raw_dir, w5_authority["record"])
    w7_authority = _m6b_w8a_w7_compact_authority(w7_compact)
    w7_record = w7_authority["sample"]["artifacts"]["residual"]
    w7_residual, w7_residual_artifact = _m6b_w9a_load_array(w7_raw_dir, w7_record, w7_record["path"])
    residuals = {
        "control_w5_iter200": w5["frozen_residual"],
        "target_w7_cumulative400": w7_residual,
    }
    span = __import__("src.solvers.krylov_span_diagnostic", fromlist=["*"])
    first = span.analyze_v_basis(
        Path(basis["path"]), residuals, rows=M6B_GLOBAL_ROWS,
        columns=M6B_W10A_COLUMNS, row_block=M6B_W10A_ROW_BLOCK,
    )
    q = w5["frozen_residual"] / np.linalg.norm(w5["frozen_residual"])
    core_measurements = first.get("measurements", {})
    control_core = core_measurements.get("control_w5_iter200")
    control_span_ready = bool(
        first.get("gram_valid") is True
        and first.get("rank") == M6B_W10A_COLUMNS
        and isinstance(control_core, Mapping)
        and control_core.get("finite") is True
        and _finite_number(control_core.get("normal_closure"))
        and control_core["normal_closure"] <= 1.0e-11
        and _finite_number(control_core.get("rho_full"))
        and control_core["rho_full"] <= 1.0e-10
    )
    measurements = {}
    for name in residuals:
        core_measurement = core_measurements.get(name)
        if not isinstance(core_measurement, Mapping):
            measurements[name] = _m6b_w10a_unavailable_measurement("projection_unavailable")
            continue
        q_overlap_energy = float(abs(np.vdot(q, residuals[name])) ** 2 / np.linalg.norm(residuals[name]) ** 2)
        measurements[name] = _m6b_w10a_measurement_record(
            core_measurement,
            q_overlap_energy,
            span,
            allow_actionable=bool(control_span_ready and core_measurement.get("finite") is True),
        )
    repeat_measurements = {
        name: span.project_from_gram(
            first["gram_hermitian"], first["h"][name],
            float(np.linalg.norm(residuals[name])), float(first["singular_values"][-1])
        ) for name in residuals
    } if first.get("gram_valid") is True and first.get("rank") == M6B_W10A_COLUMNS else {}
    repeat_exact = bool(
        set(core_measurements) == set(residuals)
        and set(repeat_measurements) == set(residuals)
        and all(
            all(
                core_measurements[name].get(key) == repeat_measurements[name].get(key)
                for key in ("finite", "normal_closure", "captured_energy_ratio", "rho_full", "coefficient_norm")
            )
            for name in residuals
            if isinstance(core_measurements.get(name), Mapping)
        )
    )
    numeric_gate = _m6b_w10a_numeric_gate(first, measurements, repeat_exact)
    source_end = h2b._light_source()
    source_ok = _m6b_w6a_source_valid(source_end) and source_end.get("source_commit_full_sha") == expected_source_sha
    checks = dict(numeric_gate["checks"])
    checks.update({"authority": True, "scratch": True, "source": source_ok})
    passed = bool(numeric_gate["pass"] and source_ok)
    non_target_checks_pass = all(value for name, value in checks.items() if name != "target_rho")
    classification = (
        "W10A_QUALIFIED_FOR_MAPPING"
        if passed
        else "W10A_OPTIMISTIC_TARGET_RHO_FAIL"
        if checks.get("target_rho") is False and non_target_checks_pass
        else "W10A_AUTHORITY_OR_NUMERIC_FAIL"
    )
    result = {
        "schema": M6B_W10A_CHECK_SCHEMA,
        "phase": M6B_W10A_PHASE,
        "status": "diagnostic_complete" if passed else "gate_failed",
        "classification": classification,
        "diagnostic_only": True,
        "w10a_pass": passed,
        "qualified_for_operator_mapping": passed,
        "formal_pass": False,
        "pde_pass": False,
        "official_rta": False,
        "current_scratch_hash_bound": True,
        "historical_producer_hash_available": False,
        "expected_source_sha": expected_source_sha,
        "source_at_start": source_start,
        "source_at_end": source_end,
        "authorities": {
            "w5_compact": {"path": w5_authority["path"], "file_sha256": w5_authority["file_sha256"], "producer_source_sha": M6B_W6A_W5_SOURCE_SHA},
            "w7_compact": {"path": str(Path(w7_compact).resolve()), "file_sha256": w7_authority["artifact"]["sha256"], "producer_source_sha": M6B_W8A_W7_SOURCE_SHA},
            "w5_raw_dir": str(Path(w5_raw_dir).resolve()),
            "w7_raw_dir": str(Path(w7_raw_dir).resolve()),
        },
        "basis_current": basis,
        "w5_residual_artifact": w5["samples"]["200"]["residual"],
        "w7_residual_artifact": w7_residual_artifact,
        "analysis": {
            "finite": first["finite"],
            "rank": first["rank"],
            "columns": first["columns"],
            "singular_values": (
                [float(value) for value in first["singular_values"]]
                if all(_finite_number(value) for value in first["singular_values"])
                else []
            ),
            "rank_threshold": float(first["rank_threshold"]) if _finite_number(first["rank_threshold"]) else None,
            "condition_number": float(first["condition_number"]) if _finite_number(first["condition_number"]) else None,
            "gram_hermitian_defect": float(first["gram_hermitian_defect"]),
            "eig_min": float(first["eig_min"]) if _finite_number(first["eig_min"]) else None,
            "eig_max": float(first["eig_max"]) if _finite_number(first["eig_max"]) else None,
            "negative_eigenvalue_limit": float(first["negative_eigenvalue_limit"]) if _finite_number(first["negative_eigenvalue_limit"]) else None,
            "gram_valid": first["gram_valid"],
            "audit": first["audit"],
            "pass": first["pass"],
            "problems": first["problems"],
        },
        "measurements": measurements,
        "repeat_exact": repeat_exact,
        "numeric_gate": numeric_gate,
        "checks": checks,
        "problems": numeric_gate["problems"] + ([] if source_ok else ["source"]),
        "limits": {"rank": M6B_W10A_COLUMNS, "normal_closure": 1.0e-11, "r5_full_rho": 1.0e-10, "control_rho_optimistic": M6B_W10A_CONTROL_RHO_LOWER, "target_rho_optimistic": M6B_W10A_TARGET_RHO_LIMIT},
        "memory": {
            "basis_memmap": True,
            "basis_in_memory": False,
            "retained_heap_basis_bytes": 0,
            "mapped_file_bytes": basis["bytes"],
            "explicit_copied_block_bytes": first["audit"]["explicit_copied_block_bytes"],
            "explicit_copied_block_scope": first["audit"]["explicit_copied_block_scope"],
            "conjugate_blas_temporaries_included": False,
            "process_tree_peak_source": "external measurement; not measured by W10A",
            "gram_bytes": first["audit"]["gram_bytes"],
            "mapped_pages_count_toward_process_rss": True,
        },
        "scope": {"algorithm": "optimistic W5 V-span recycle upper bound", "basis_columns": M6B_W10A_COLUMNS, "row_block": M6B_W10A_ROW_BLOCK, "operator_mapping_available": False, "action_calls": 0, "ksp_calls": 0, "pde_calls": 0},
        "elapsed_seconds": time.perf_counter() - started,
    }
    _write_json(output, _attach_evidence(result))
    return 0 if passed else 1


def _m6b_w8a_w8b_authority_valid(
    value: Any, *, w8a_raw_dir: Path, expected_source_sha: str
) -> bool:
    if not isinstance(value, Mapping) or not _evidence_valid(value):
        return False
    formal_authority = (
        value.get("schema") == M6B_W8A_FORMAL_CHECK_SCHEMA
        and value.get("formal_pass") is True
        and value.get("w8a_formal_pass") is True
        and value.get("pde_pass") is False
        and value.get("producer_source_sha") == expected_source_sha
        and value.get("raw_dir") == str(Path(w8a_raw_dir).resolve())
    )
    recovery_checks = value.get("checks")
    recovery_authority = (
        value.get("schema") == M6B_W8A_RECOVERY_SCHEMA
        and value.get("status") == "recovery_complete"
        and value.get("classification") == "RECOVERED_QUALIFIED_FOR_W8B"
        and value.get("recovered_numeric_gate_pass") is True
        and value.get("companion_gate_pass") is True
        and value.get("qualified_for_w8b") is True
        and value.get("formal_pass") is False
        and value.get("pde_pass") is False
        and value.get("official_rta") is False
        and value.get("original_builder_execution_pass") is False
        and value.get("old_watchdog_status") == "gate_failed"
        and value.get("producer_source_sha") == M6B_W8A_RECOVERY_PRODUCER_SHA
        and value.get("companion_source_sha") == expected_source_sha
        and value.get("raw_dir") == str(Path(w8a_raw_dir).resolve())
        and isinstance(recovery_checks, Mapping)
        and {
            "producer_sha", "paths", "artifact_hashes", "source", "old_watchdog",
            "resource", "progress", "failure_boundary", "w6a_authority", "jit",
            "fixed_identity", "store", "retained_payload", "prediction", "companion",
            "source_delta", "recovery_checker_source",
        } <= set(recovery_checks)
        and all(item is True for item in recovery_checks.values())
        and value.get("problems") == []
    )
    source_delta = value.get("source_delta")
    companion = value.get("companion_verification")
    producer = value.get("producer_measurement")
    checker_source = value.get("recovery_checker_source")
    recovery_authority = recovery_authority and bool(
        isinstance(source_delta, Mapping)
        and source_delta.get("pass") is True
        and source_delta.get("ancestor") is True
        and source_delta.get("paths_unchanged") is True
        and source_delta.get("producer_source_sha") == M6B_W8A_RECOVERY_PRODUCER_SHA
        and source_delta.get("current_source_sha") == expected_source_sha
        and source_delta.get("allowlist") == sorted(M6B_W8A_RECOVERY_ALLOWED_CHANGED_PATHS)
        and isinstance(companion, Mapping)
        and companion.get("pass") is True
        and isinstance(companion.get("checks"), Mapping)
        and bool(companion["checks"])
        and all(item is True for item in companion["checks"].values())
        and isinstance(companion.get("summary"), Mapping)
        and isinstance(companion["summary"].get("sentinel_actions"), list)
        and len(companion["summary"]["sentinel_actions"])
        == len(M6B_W8A_COMPANION_SENTINEL_COLUMNS)
        and [
            item.get("column_index")
            for item in companion["summary"]["sentinel_actions"]
            if isinstance(item, Mapping)
        ] == list(M6B_W8A_COMPANION_SENTINEL_COLUMNS)
        and all(
            isinstance(item, Mapping)
            and item.get("finite") is True
            and _finite_number(item.get("relative_error"))
            and item["relative_error"] <= 1.0e-11
            and _m6b_w6a_valid_sha(item.get("old_az_array_sha256"))
            for item in companion["summary"]["sentinel_actions"]
        )
        and isinstance(producer, Mapping)
        and producer.get("source_sha") == M6B_W8A_RECOVERY_PRODUCER_SHA
        and producer.get("watchdog_status") == "gate_failed"
        and producer.get("artifact_hashes") is True
        and producer.get("old_watchdog") is True
        and producer.get("resource") is True
        and producer.get("failure_boundary") is True
        and isinstance(producer.get("progress"), Mapping)
        and producer["progress"].get("pass") is True
        and producer["progress"].get("last_event") == "gram_ready"
        and isinstance(producer.get("store_validation"), Mapping)
        and producer["store_validation"].get("pass") is True
        and _m6b_w6a_source_valid(checker_source)
        and checker_source.get("source_commit_full_sha") == expected_source_sha
    )
    return bool(formal_authority or recovery_authority)


def _run_m6b_w8b_s0(
    w8a_raw_dir: Path,
    w8a_formal_output: Path,
    w6a_raw_dir: Path,
    w5_raw_dir: Path,
    w7_raw_dir: Path,
    w5_compact: Path,
    w7_compact: Path,
    output: Path,
    expected_source_sha: str,
) -> int:
    """Run the fixed W8B offline comparison without FE/action calls."""

    import numpy as np
    if output.exists():
        raise FileExistsError(f"W8B output exists: {output}")
    formal = _read_json(w8a_formal_output)
    if not _m6b_w8a_w8b_authority_valid(
        formal, w8a_raw_dir=w8a_raw_dir, expected_source_sha=expected_source_sha
    ):
        raise RuntimeError("W8B requires a passing W8A formal or qualified recovery")
    w5 = _m6b_w6a_w5_compact_authority()
    if Path(w5_compact).resolve() != Path(w5["path"]).resolve():
        raise RuntimeError("W8B W5 compact path is not the frozen authority")
    w7 = _m6b_w8a_w7_compact_authority(w7_compact)
    w5_record = w5["record"]["screen"]["samples"]["200"]["artifacts"]["residual"]
    w7_record = w7["sample"]["artifacts"]["residual"]
    w5_values = _m6b_w8b_load_residual(w5_raw_dir, w5_record, array_hash=_m6b_w6a_w5_legacy_raw_array_sha256)
    w7_values = _m6b_w8b_load_residual(
        w7_raw_dir,
        w7_record,
        # W7 compact/checkpoint authority uses raw contiguous array bytes.
        array_hash=_m6b_w6a_w5_legacy_raw_array_sha256,
    )
    from src.solvers.hcurl_m6b_w8a_z_bubble_range import W8AMultiOrderRangeDiagnostic
    legacy_store_dir = _m6b_w8b_legacy_store_dir(w6a_raw_dir)
    diagnostic = W8AMultiOrderRangeDiagnostic.load(
        Path(w8a_raw_dir) / "sparse_range_store" / "manifest.json",
        legacy_store_dir=legacy_store_dir,
    )
    try:
        measurements = {
            "w5_iter200": diagnostic.compare_range_orders(w5_values),
            "w7_cumulative400": diagnostic.compare_range_orders(w7_values),
        }
    finally:
        diagnostic.close()
    gate = _m6b_w8a_numeric_gate(measurements)
    source = __import__("benchmarks.run_task037_extra_h2b", fromlist=["*"])._light_source()
    source_ok = _m6b_w6a_source_valid(source) and source.get("source_commit_full_sha") == expected_source_sha
    result = {
        "schema": M6B_W8B_SCHEMA,
        "phase": M6B_W8B_PHASE,
        "status": "diagnostic_complete" if gate["pass"] and source_ok else "gate_failed",
        "classification": "QUALIFIED_FOR_W8C" if gate["pass"] and source_ok else "W8B_NUMERIC_OR_AUTHORITY_FAIL",
        "diagnostic_only": True,
        "formal_pass": False,
        "pde_pass": False,
        "official_rta": False,
        "numeric_gate": gate,
        "measurements": measurements,
        "authorities": {
            "w5_compact": {"path": w5["path"], "file_sha256": w5["file_sha256"], "producer_source_sha": M6B_W8A_W5_SOURCE_SHA},
            "w7_compact": w7["artifact"],
            "w8a_formal": _artifact(Path(w8a_formal_output).parent, Path(w8a_formal_output).name),
        },
        "source_at_end": source,
        "expected_source_sha": expected_source_sha,
        "scope": _m6b_w8a_scope(prediction={}),
    }
    _write_json(output, _attach_evidence(result))
    return 0 if result["classification"] == "QUALIFIED_FOR_W8C" else 1


def _run_m6b_w6b_s0(
    w6a_raw_dir: Path,
    w5_raw_dir: Path,
    output: Path,
    expected_source_sha: str,
) -> int:
    """Run the fixed read-only W6B-S0 diagnosis on frozen W6A scratch."""

    import time

    if output.exists():
        raise FileExistsError(f"W6B-S0 output already exists: {output}")
    h2b = __import__("benchmarks.run_task037_extra_h2b", fromlist=["*"])
    source_start = h2b._light_source()
    if (
        source_start.get("source_commit_full_sha") != expected_source_sha
        or not _m6b_w6a_source_valid(source_start)
    ):
        raise RuntimeError("W6B-S0 source identity is not clean or expected")
    w5_authority = _m6b_w6a_w5_compact_authority()
    w6a_summary_path = Path(w6a_raw_dir).resolve() / "w6a_summary.json"
    w6a_summary = _read_json(w6a_summary_path)
    w6a_summary_artifact = _artifact(Path(w6a_raw_dir).resolve(), "w6a_summary.json")
    residual_artifacts = w6a_summary.get("residual_artifacts")
    if not (
        _m6b_w6b_s0_w6a_summary_authority_valid(
            w6a_summary, w6a_summary_artifact
        )
        and _m6b_w6a_w5_residual_files_valid(
            residual_artifacts,
            Path(w6a_raw_dir).resolve(),
            Path(w5_raw_dir).resolve(),
            compact_record=w5_authority["record"],
        )
    ):
        raise RuntimeError("W6B-S0 frozen W5 residual authority is not closed")
    from src.solvers.hcurl_m6b_w6b_s0_spectral import run_w6b_s0

    started = time.perf_counter()
    result = run_w6b_s0(
        w6a_raw_dir,
        w5_raw_dir,
        expected_source_sha=expected_source_sha,
    )
    source_end = h2b._light_source()
    source_ok = bool(
        _m6b_w6a_source_valid(source_end)
        and source_end.get("source_commit_full_sha") == expected_source_sha
    )
    result["source_at_start"] = source_start
    result["source_at_end"] = source_end
    result["source_clean"] = source_ok
    result["frozen_w5_compact_authority"] = {
        "path": w5_authority["path"],
        "file_sha256": w5_authority["file_sha256"],
        "producer_source_sha": M6B_W6A_W5_SOURCE_SHA,
    }
    result["frozen_w6a_producer_authority"] = {
        "summary_artifact": w6a_summary_artifact,
        "producer_source_sha": M6B_W6B_S0_W6A_PRODUCER_SOURCE_SHA,
        "status": w6a_summary["status"],
        "numeric_gate_pass": w6a_summary["numeric_gate"]["pass"],
    }
    result["elapsed_wall_seconds"] = float(time.perf_counter() - started)
    result["diagnostic_pass"] = bool(result["diagnostic_pass"] and source_ok)
    result["status"] = (
        "diagnostic_complete" if result["diagnostic_pass"] else "gate_failed"
    )
    _write_json(output, _attach_evidence(result))
    return 0 if result["diagnostic_pass"] else 1


def _m6b_w8a_predicted_live_set(
    *,
    old_retained_bytes: int,
    new_retained_bytes: int,
    old_work_bytes: int,
    new_work_bytes: int,
) -> dict[str, Any]:
    values = (old_retained_bytes, new_retained_bytes, old_work_bytes, new_work_bytes)
    if any(type(value) is not int or value < 0 for value in values):
        raise ValueError("W8A retained/work bytes must be nonnegative integers")
    retained_delta = new_retained_bytes - old_retained_bytes
    work_delta = new_work_bytes - old_work_bytes
    if retained_delta < 0 or work_delta < 0:
        raise ValueError("W8A new-minus-old deltas must be nonnegative")
    total = int(M6B_W8A_PRODUCTION_BASE_PEAK_BYTES + retained_delta + work_delta)
    return {
        "base_measured_production_peak_bytes": M6B_W8A_PRODUCTION_BASE_PEAK_BYTES,
        "base_peak_authority": "W7_S1_W5_CALIBRATED_PEAK_BYTES",
        "old_retained_bytes": old_retained_bytes,
        "new_retained_bytes": new_retained_bytes,
        "old_work_bytes": old_work_bytes,
        "new_work_bytes": new_work_bytes,
        "new_minus_old_retained_bytes": retained_delta,
        "new_minus_old_work_bytes": work_delta,
        "predicted_live_set_bytes": total,
        "limit_bytes": M6B_W8A_PREDICTED_LIVE_SET_LIMIT_BYTES,
        "gate": total <= M6B_W8A_PREDICTED_LIVE_SET_LIMIT_BYTES,
        "derived_not_measured": True,
        "is_measurement": False,
        "prediction_scope": "production_w8a_carrier_delta_from_w7_s1_w5_process_tree_calibration",
        "w6a_builder_peak_is_not_production_base": True,
    }


def _m6b_w8a_scope(*, prediction: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": M6B_W8A_SCHEMA,
        "degree": M6B_DEGREE,
        "h_nm": M6B_H_NM,
        "global_cells": M6B_GLOBAL_CELLS,
        "global_rows": M6B_GLOBAL_ROWS,
        "constraint_count": M6B_CONSTRAINTS,
        "factor_count": M6B_FACTOR_COUNT,
        "factor_reuse_count": M6B_FACTOR_REUSE,
        "beta": 1.0,
        "fine_space": "uncondensed_fullspace",
        "operator": "A=Kcurl-k0^2*M_epsilon+A_DtN",
        "global_matrix": False,
        "augmented_matrix": False,
        "static_condensation": False,
        "trace_slab_pc": False,
        "schur": False,
        "dtn_matrix_free": True,
        "mpi_size": 1,
        "legacy_columns": M6B_W8A_LEGACY_COLUMNS,
        "added_columns": M6B_W8A_ADDED_COLUMNS,
        "columns": M6B_W8A_COLUMNS,
        "diffraction_orders": list(M6B_W8A_ORDERS),
        "component": M6B_W8A_COMPONENT,
        "intervals": M6B_W8A_INTERVALS,
        "bubble_degrees": list(M6B_W8A_BUBBLE_DEGREES),
        "fixed_order": True,
        "scan": False,
        "az_builder_only": True,
        "az_production_retained": False,
        "dense_z_retained": False,
        "dense_az_retained": False,
        "prediction": dict(prediction),
        "formal_pass": False,
        "pde_pass": False,
    }


def _m6b_w8a_progress_emit(path: Path, event: str, **fields: Any) -> None:
    record = {
        "schema": f"{M6B_W8A_SCHEMA}.progress.v1",
        "phase": M6B_W8A_PHASE,
        "event": event,
        **fields,
    }
    with Path(path).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _m6b_w8a_progress_valid(path: Path) -> dict[str, Any]:
    try:
        records = [
            json.loads(line)
            for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        events = [record.get("event") for record in records]
        fixed = (
            "authority_validated",
            "mesh_ready",
            "space_ready",
            "floquet_mpc_ready",
            "cache_ready",
            "outer_ready",
            "legacy_basis_ready",
            "bubble_spec_ready",
            "bubble_columns_ready",
            "az_ready",
            "gram_ready",
            "summary_ready",
        )
        if not records or any(
            type(record) is not dict
            or record.get("schema") != f"{M6B_W8A_SCHEMA}.progress.v1"
            or record.get("phase") != M6B_W8A_PHASE
            for record in records
        ):
            raise ValueError("W8A progress record is invalid")
        positions = [events.index(event) for event in fixed]
        if positions != sorted(positions):
            raise ValueError("W8A progress order is invalid")
        bubble = [record for record in records if record.get("event") == "column_progress"]
        if not bubble or bubble[-1].get("completed") != M6B_W8A_ADDED_COLUMNS:
            raise ValueError("W8A bubble progress is incomplete")
        repeats = [record for record in records if record.get("event") == "repeat_ready"]
        if len(repeats) != len(M6B_W8A_REPEAT_COLUMNS) or [
            record.get("column_index") for record in repeats
        ] != list(M6B_W8A_REPEAT_COLUMNS):
            raise ValueError("W8A repeat progress is incomplete")
        return {"pass": True, "record_count": len(records), "events": events}
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        return {"pass": False, "problems": [f"{type(exc).__name__}:{exc}"]}


def _m6b_w8a_companion_progress_emit(path: Path, event: str, **fields: Any) -> None:
    record = {
        "schema": f"{M6B_W8A_COMPANION_SCHEMA}.progress.v1",
        "phase": M6B_W8A_COMPANION_PHASE,
        "event": event,
        **fields,
    }
    with Path(path).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _m6b_w8a_companion_progress_valid(path: Path) -> dict[str, Any]:
    expected = (
        "authority_validated",
        "mesh_ready",
        "space_ready",
        "floquet_mpc_ready",
        "cache_ready",
        "outer_ready",
        "bubble_spec_ready",
        "fe_audit_ready",
        "sentinel_ready",
        "summary_ready",
    )
    try:
        records = [
            json.loads(line)
            for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        events = [record.get("event") for record in records]
        if events != list(expected) or any(
            type(record) is not dict
            or record.get("schema") != f"{M6B_W8A_COMPANION_SCHEMA}.progress.v1"
            or record.get("phase") != M6B_W8A_COMPANION_PHASE
            for record in records
        ):
            raise ValueError("W8A companion progress is invalid")
        return {"pass": True, "record_count": len(records), "events": events}
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        return {"pass": False, "problems": [f"{type(exc).__name__}:{exc}"]}


def _m6b_w8a_recovery_source_delta(current_source_sha: str) -> dict[str, Any]:
    import shutil
    import subprocess

    result: dict[str, Any] = {
        "producer_source_sha": M6B_W8A_RECOVERY_PRODUCER_SHA,
        "current_source_sha": current_source_sha,
        "allowlist": sorted(M6B_W8A_RECOVERY_ALLOWED_CHANGED_PATHS),
        "ancestor": False,
        "changed_paths": [],
        "paths_unchanged": False,
        "pass": False,
    }
    if not (
        isinstance(current_source_sha, str)
        and len(current_source_sha) == 40
        and all(char in "0123456789abcdef" for char in current_source_sha)
    ):
        return result
    git = shutil.which("git")
    if git is None:
        return result
    git = os.path.abspath(git)
    common = [git, "--git-dir", str(ROOT / ".git-codex"), "--work-tree", str(ROOT)]
    try:
        ancestor = subprocess.run(
            [*common, "merge-base", "--is-ancestor", M6B_W8A_RECOVERY_PRODUCER_SHA, current_source_sha],
            capture_output=True,
            text=True,
            close_fds=False,
        )
        changed = subprocess.run(
            [*common, "diff", "--name-only", M6B_W8A_RECOVERY_PRODUCER_SHA, current_source_sha],
            check=True,
            capture_output=True,
            text=True,
            close_fds=False,
        )
    except (OSError, subprocess.CalledProcessError):
        return result
    paths = sorted(line for line in changed.stdout.splitlines() if line)
    result.update({
        "ancestor": ancestor.returncode == 0,
        "changed_paths": paths,
        "paths_unchanged": set(paths) <= M6B_W8A_RECOVERY_ALLOWED_CHANGED_PATHS,
    })
    result["pass"] = bool(result["ancestor"] and result["paths_unchanged"])
    return result


def _m6b_w8a_companion_architecture_valid(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    exact = {
        "fine_space": "uncondensed_fullspace",
        "global_matrix": False,
        "augmented_matrix": False,
        "static_condensation": False,
        "trace_slab_pc": False,
        "schur": False,
        "dtn_matrix_free": True,
        "dense_z_retained": False,
        "dense_az_retained": False,
        "az_builder_only": True,
        "az_production_retained": False,
        "explicit_C_materialized_count": 0,
        "explicit_D_materialized_count": 0,
    }
    return all(value.get(key) == expected for key, expected in exact.items())


def _m6b_w8a_w6a_authority(w6a_raw_dir: Path) -> dict[str, Any]:
    root = Path(w6a_raw_dir).resolve()
    summary_path = root / "w6a_summary.json"
    summary_artifact = _artifact(root, "w6a_summary.json")
    summary = _read_json(summary_path)
    if not (
        summary_artifact.get("sha256") == M6B_W8A_W6A_SUMMARY_SHA256
        and _evidence_valid(summary)
        and summary.get("schema") == M6B_W6A_SCHEMA
        and summary.get("status") == "gate_failed"
        and summary.get("numeric_gate", {}).get("pass") is False
        and summary.get("source_at_start", {}).get("source_commit_full_sha")
        == M6B_W8A_W6A_SOURCE_SHA
        and summary.get("source_at_end", {}).get("source_commit_full_sha")
        == M6B_W8A_W6A_SOURCE_SHA
        and _m6b_w6a_source_valid(summary.get("source_at_start"))
        and _m6b_w6a_source_valid(summary.get("source_at_end"))
    ):
        raise ValueError("W8A frozen W6A producer authority is not closed")
    return {"path": str(summary_path), "artifact": summary_artifact, "summary": summary}


def _m6b_w8a_w7_compact_authority(compact_path: Path) -> dict[str, Any]:
    compact_path = Path(compact_path).resolve()
    expected = (ROOT / M6B_W8A_W7_COMPACT_RELATIVE_PATH).resolve()
    artifact = _artifact(ROOT, M6B_W8A_W7_COMPACT_RELATIVE_PATH)
    record = _read_json(compact_path)
    if not (
        compact_path == expected
        and artifact.get("sha256") == M6B_W8A_W7_COMPACT_SHA256
        and _evidence_valid(record)
        and record.get("classification") == "NUMERIC_FAIL"
        and record.get("producer_source_sha") == M6B_W8A_W7_SOURCE_SHA
        and record.get("numeric_ok") is False
    ):
        raise ValueError("W8B frozen W7 compact authority is not closed")
    sample = record.get("measurements", {}).get("checkpoints", {}).get("200")
    if not isinstance(sample, Mapping) or sample.get("cumulative_iteration") != 400:
        raise ValueError("W8B W7 cumulative-400 authority is missing")
    residual = sample.get("artifacts", {}).get("residual")
    if not isinstance(residual, Mapping):
        raise ValueError("W8B W7 residual authority is missing")
    return {"path": str(compact_path), "artifact": artifact, "record": record, "sample": sample}


def _m6b_w8b_legacy_store_dir(w6a_raw_dir: Path) -> Path:
    root = Path(w6a_raw_dir).resolve()
    store = root / "sparse_range_store"
    if not store.is_dir():
        raise FileNotFoundError("W8B W6A raw root has no sparse_range_store")
    return store


def _m6b_w8a_legacy_store_dir(w6a_raw_dir: Path) -> Path:
    root = Path(w6a_raw_dir).resolve()
    store = _m6b_w8b_legacy_store_dir(root)
    authority = _m6b_w8a_w6a_authority(root)
    expected = authority["summary"].get("store_manifest_artifact")
    actual = _artifact(root, "sparse_range_store/manifest.json")
    if not isinstance(expected, Mapping) or actual != expected:
        raise ValueError("W8A legacy store is not the frozen W6A store")
    return store


def _m6b_w8a_numeric_gate(results: Mapping[str, Any]) -> dict[str, Any]:
    required = {"w5_iter200", "w7_cumulative400"}
    values: dict[str, dict[str, float]] = {}
    problems: list[str] = []
    if not isinstance(results, Mapping) or set(results) != required:
        problems.append("residual_set")
    else:
        for label in sorted(required):
            item = results[label]
            if not isinstance(item, Mapping):
                problems.append(label)
                continue
            rho390 = item.get("rho390")
            rho530 = item.get("rho530")
            normal_closure = item.get("normal_closure")
            if not (_finite_number(rho390) and _finite_number(rho530) and _finite_number(normal_closure)):
                problems.append(label)
                continue
            values[label] = {
                "rho390": float(rho390),
                "rho530": float(rho530),
                "normal_closure": float(normal_closure),
            }
    if set(values) == required:
        for label, item in values.items():
            if item["normal_closure"] > M6B_W8A_NORMAL_CLOSURE_LIMIT:
                problems.append(f"{label}_normal_closure")
            if item["rho530"] > item["rho390"] + 1.0e-12:
                problems.append(f"{label}_not_nested")
        w7 = values["w7_cumulative400"]
        if w7["rho530"] > 0.70:
            problems.append("w7_cumulative400_rho530")
        improvement = 1.0 - w7["rho530"] / w7["rho390"]
        if improvement < 0.15:
            problems.append("w7_cumulative400_improvement")
    else:
        improvement = None
    return {
        "pass": not problems,
        "problems": sorted(set(problems)),
        "values": values,
        "w7_cumulative400_relative_improvement": improvement,
        "limits": {"w7_cumulative400_rho530": 0.70, "relative_improvement": 0.15},
    }


def _m6b_w6b_s0_w6a_summary_authority_valid(
    summary: Any, artifact: Any
) -> bool:
    if not (
        isinstance(summary, Mapping)
        and isinstance(artifact, Mapping)
        and artifact.get("present") is True
        and artifact.get("path") == "w6a_summary.json"
        and artifact.get("sha256") == M6B_W6B_S0_W6A_SUMMARY_FILE_SHA256
        and summary.get("schema") == M6B_W6A_SCHEMA
        and _evidence_valid(summary)
        and summary.get("status") == "gate_failed"
    ):
        return False
    numeric_gate = summary.get("numeric_gate")
    source_start = summary.get("source_at_start")
    source_end = summary.get("source_at_end")
    return bool(
        isinstance(numeric_gate, Mapping)
        and numeric_gate.get("pass") is False
        and _m6b_w6a_source_valid(source_start)
        and _m6b_w6a_source_valid(source_end)
        and source_start.get("source_commit_full_sha")
        == M6B_W6B_S0_W6A_PRODUCER_SOURCE_SHA
        and source_end.get("source_commit_full_sha")
        == M6B_W6B_S0_W6A_PRODUCER_SOURCE_SHA
    )


def _m6b_w3_numeric_gate(
    samples: Mapping[str, Any] | None,
) -> dict[str, Any]:
    from src.solvers.hcurl_h2b_m6b_shifted_patch_pc import (
        evaluate_m6b_numeric_screen_gate,
    )

    return evaluate_m6b_numeric_screen_gate(samples)


def _m6b_screen_audit_jsonable(h2a: Any, value: Any) -> Any:
    return h2a._jsonable(value)


def _m6b_w3_screen_orchestration(
    *,
    projected_pc: Any,
    outer_mat: Any,
    outer_context: Any,
    rhs_vec: Any,
    checkpoint_dir: Path,
    solver: str = "fgmres",
    checkpoint_observer: Callable[[Mapping[str, Any]], None] | None = None,
) -> tuple[Any, dict[str, Any]]:
    """Connect the projected production PC and fixed screen after RHS setup."""

    from src.solvers.hcurl_h2b_m6b_shifted_patch_pc import (
        M6BShiftedPCContext,
        run_m6b_right_fbcgs_screen,
        run_m6b_right_fgmres_screen,
    )

    audit = getattr(projected_pc, "audit", None)
    if not isinstance(audit, Mapping) or audit.get("fixed_order") != "projected_range_complement":
        raise ValueError("M6B W3 requires the projected range production PC")
    pc_context = M6BShiftedPCContext(projected_pc)
    if solver == "fgmres":
        screen_runner = run_m6b_right_fgmres_screen
    elif solver == "fbcgs":
        screen_runner = run_m6b_right_fbcgs_screen
    else:
        raise ValueError("M6B screen solver is not fixed")
    screen = screen_runner(
        outer_mat,
        rhs_vec,
        pc_context=pc_context,
        checkpoint_dir=checkpoint_dir,
        operator_context=outer_context,
        checkpoint_observer=checkpoint_observer,
    )
    return pc_context, screen


def _m6b_worker_numeric_pass_fields(
    *, screen: bool, error: str | None, gate: Mapping[str, Any]
) -> tuple[bool, bool]:
    """Separate W3 screen status from the W2/W2R diagnostic status."""

    passed = bool(error is None and gate["pass"])
    return bool(not screen and passed), bool(screen and passed)


def _m6b_w2r_positive_record() -> dict[str, Any]:
    path = ROOT / M6B_W3_COMPACT_PATH
    if not path.is_file() or _sha256_file(path) != M6B_W3_COMPACT_FILE_SHA256:
        raise ValueError("M6B W2R positive compact authority differs")
    value = _read_json(path)
    checks = value.get("checks")
    worker = value.get("worker")
    watchdog = value.get("watchdog")
    source = value.get("source")
    if not (
        value.get("schema") == "task037.extra.m6b.w2r.projected-range.compact.v1"
        and _evidence_valid(value)
        and value.get("status") == "diagnostic_pass"
        and value.get("pde_pass") is False
        and isinstance(checks, Mapping)
        and checks
        and all(item is True for item in checks.values())
        and isinstance(worker, Mapping)
        and worker.get("diagnostic_numeric_pass") is True
        and worker.get("w2r_pass") is False
        and worker.get("formal_pass") is False
        and isinstance(watchdog, Mapping)
        and watchdog.get("formal_pass") is True
        and watchdog.get("w2r_pass") is True
        and watchdog.get("pde_pass") is False
        and isinstance(source, Mapping)
        and source.get("commit_full_sha") == M6B_W3_W2R_SOURCE_SHA
    ):
        raise ValueError("M6B W2R positive compact authority is not closed")
    return {
        "path": str(path),
        "sha256": M6B_W3_COMPACT_FILE_SHA256,
        "evidence_sha256": value["evidence_sha256"],
        "source_sha": source["commit_full_sha"],
        "watchdog_formal_pass": True,
        "worker_diagnostic_numeric_pass": True,
    }


def _m6b_w2r_old_negative_valid(
    raw: Any,
    watchdog: Any,
    raw_sha256: Any,
    watchdog_sha256: Any,
) -> bool:
    if (
        raw_sha256 != M6B_W2R_OLD_RAW_SUMMARY_SHA256
        or watchdog_sha256 != M6B_W2R_OLD_WATCHDOG_SUMMARY_SHA256
        or not isinstance(raw, Mapping)
        or not isinstance(watchdog, Mapping)
        or not _evidence_valid(raw)
        or not _evidence_valid(watchdog)
    ):
        return False
    raw_gate = raw.get("gate")
    raw_checks = raw_gate.get("checks") if isinstance(raw_gate, Mapping) else None
    raw_start = raw.get("source_at_start")
    raw_end = raw.get("source_at_end")
    watchdog_process = watchdog.get("process")
    watchdog_start = watchdog.get("source_start")
    watchdog_end = watchdog.get("source_end")
    watchdog_worker_summary = watchdog.get("worker_summary")
    watchdog_gate = (
        watchdog_worker_summary.get("gate")
        if isinstance(watchdog_worker_summary, Mapping)
        else None
    )
    watchdog_checks = (
        watchdog_gate.get("checks") if isinstance(watchdog_gate, Mapping) else None
    )
    return bool(
        raw.get("status") == "gate_failed"
        and raw.get("error") is None
        and raw.get("diagnostic_numeric_pass") is False
        and raw.get("w2_pass") is False
        and raw.get("formal_pass") is False
        and raw.get("pde_pass") is False
        and _m6b_w2_source_identity_valid(raw_start, M6B_W2R_OLD_NEGATIVE_SOURCE_SHA)
        and _m6b_w2_source_identity_valid(raw_end, M6B_W2R_OLD_NEGATIVE_SOURCE_SHA)
        and isinstance(raw_gate, Mapping)
        and raw_gate.get("pass") is False
        and raw_gate.get("problems") == ["composed_rho_gate"]
        and isinstance(raw_checks, Mapping)
        and raw_checks.get("composed_rho_gate") is False
        and all(
            raw_checks.get(key) is True
            for key in raw_checks
            if key != "composed_rho_gate"
        )
        and watchdog.get("formal_pass") is False
        and watchdog.get("w2_pass") is False
        and watchdog.get("pde_pass") is False
        and watchdog.get("wrapper_error") is None
        and _m6b_w2_source_identity_valid(
            watchdog_start, M6B_W2R_OLD_NEGATIVE_SOURCE_SHA
        )
        and _m6b_w2_source_identity_valid(
            watchdog_end, M6B_W2R_OLD_NEGATIVE_SOURCE_SHA
        )
        and isinstance(watchdog_process, Mapping)
        and watchdog_process.get("return_code") == 1
        and watchdog_process.get("termination") is None
        and watchdog_process.get("peak_rss_bytes")
        == M6B_W2R_OLD_NEGATIVE_PEAK_RSS_BYTES
        and watchdog_process.get("swap_bytes") == 0
        and isinstance(watchdog_checks, Mapping)
        and watchdog_checks.get("composed_rho_gate") is False
        and all(
            watchdog_checks.get(key) is True
            for key in watchdog_checks
            if key != "composed_rho_gate"
        )
    )


def _m6b_w2r_old_negative_record() -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[1]
    raw_path = (
        repo_root
        / "benchmarks/artifacts/task037_extra_development/"
        "m6b_w2_64e4794_diagnostic_run1/m6b_w2_summary.json"
    )
    watchdog_path = Path(
        "/tmp/task037_m6b_w2_64e4794_watchdog/m6b_w2_watchdog_summary.json"
    )
    if not raw_path.is_file() or not watchdog_path.is_file():
        raise FileNotFoundError("W2R frozen W2 negative evidence is missing")
    raw_sha256 = _sha256_file(raw_path)
    watchdog_sha256 = _sha256_file(watchdog_path)
    raw = _read_json(raw_path)
    watchdog = _read_json(watchdog_path)
    if not _m6b_w2r_old_negative_valid(
        raw, watchdog, raw_sha256, watchdog_sha256
    ):
        raise ValueError("W2R frozen W2 negative evidence is not closed")
    return {
        "source_sha": M6B_W2R_OLD_NEGATIVE_SOURCE_SHA,
        "raw_summary": {
            "path": str(raw_path),
            "present": True,
            "bytes": int(raw_path.stat().st_size),
            "sha256": raw_sha256,
            "evidence_sha256": raw["evidence_sha256"],
        },
        "watchdog_summary": {
            "path": str(watchdog_path),
            "present": True,
            "bytes": int(watchdog_path.stat().st_size),
            "sha256": watchdog_sha256,
            "evidence_sha256": watchdog["evidence_sha256"],
        },
        "only_failed_check": "composed_rho_gate",
        "peak_rss_bytes": M6B_W2R_OLD_NEGATIVE_PEAK_RSS_BYTES,
        "swap_bytes": 0,
        "termination": None,
    }


def _m6b_w2_sha_valid(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and value == value.lower()
        and all(char in "0123456789abcdef" for char in value)
    )


def _m6b_w2_source_sha_valid(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 40
        and value == value.lower()
        and all(char in "0123456789abcdef" for char in value)
    )


def _m6b_w2_source_sha_argument(value: str) -> str:
    if not _m6b_w2_source_sha_valid(value):
        raise argparse.ArgumentTypeError(
            "expected a 40-character lowercase source commit SHA"
        )
    return value


def _m6b_w2_source_identity_valid(value: Any, expected_sha: str) -> bool:
    required = {
        "source_commit_full_sha",
        "tracked_source_dirty",
        "source_worktree_dirty",
        "nonignored_untracked_paths",
        "worktree_status_porcelain",
        "git_error",
    }
    return bool(
        _m6b_w2_source_sha_valid(expected_sha)
        and isinstance(value, Mapping)
        and required <= set(value)
        and value["source_commit_full_sha"] == expected_sha
        and value["tracked_source_dirty"] is False
        and value["source_worktree_dirty"] is False
        and value["nonignored_untracked_paths"] == []
        and value["worktree_status_porcelain"] == []
        and value["git_error"] is None
    )


def _m6b_w2_residual_artifact_valid(value: Any, iteration: int) -> bool:
    required = {"path", "absolute_path", "bytes", "sha256", "present"}
    if not isinstance(value, Mapping) or not required <= set(value):
        return False
    path = value["path"]
    absolute_path = value["absolute_path"]
    return bool(
        value["present"] is True
        and path == f"m6b_iter{iteration}_residual.npy"
        and isinstance(absolute_path, str)
        and Path(absolute_path).is_absolute()
        and Path(absolute_path).name == path
        and type(value["bytes"]) is int
        and value["bytes"] > 0
        and _m6b_w2_sha_valid(value["sha256"])
    )


def _m6b_w2_measurement_valid(value: Any) -> bool:
    required = {
        "schema",
        "iteration",
        "residual_array_sha256",
        "residual_artifact",
        "finite",
        "rho_local_only",
        "rho_range_only",
        "rho_composed",
        "linear_action_closure",
        "normal_projected_component_ratio",
        "action_counts",
        "repeat_identical",
        "correction_sha256",
        "repeat_correction_sha256",
        "rhs_sha256",
        "local_correction_sha256",
        "local_action_sha256",
        "local_residual_sha256",
        "range_only_correction_sha256",
        "range_only_action_sha256",
        "range_correction_sha256",
        "range_action_sha256",
        "final_correction_sha256",
        "final_action_sha256",
        "final_residual_sha256",
        "final_range_correction_sha256",
        "final_range_action_sha256",
    }
    if not isinstance(value, Mapping) or not required <= set(value):
        return False
    action_counts = value["action_counts"]
    action_count_keys = {
        "local_apply",
        "physical_outer_action",
        "range_apply",
    }
    if not (
        isinstance(action_counts, Mapping)
        and action_count_keys <= set(action_counts)
        and action_counts["local_apply"] == 1
        and action_counts["physical_outer_action"] == 5
        and action_counts["range_apply"] == 3
    ):
        return False
    quantities = (
        "rho_local_only",
        "rho_range_only",
        "rho_composed",
        "linear_action_closure",
        "normal_projected_component_ratio",
    )
    hash_fields = tuple(key for key in required if key.endswith("_sha256"))
    return bool(
        value["schema"] == "task037.extra.h2b.m6b.shifted-range-pc.v1"
        and type(value["iteration"]) is int
        and _m6b_w2_sha_valid(value["residual_array_sha256"])
        and _m6b_w2_residual_artifact_valid(
            value["residual_artifact"], value["iteration"]
        )
        and value["finite"] is True
        and value["repeat_identical"] is True
        and all(_m6b_w2_sha_valid(value[key]) for key in hash_fields)
        and all(
            _finite_number(value[key]) and float(value[key]) >= 0.0
            for key in quantities
        )
    )


def _m6b_w2r_measurement_valid(value: Any) -> bool:
    required = {
        "schema",
        "iteration",
        "residual_array_sha256",
        "residual_artifact",
        "finite",
        "rho_local_only",
        "rho_range_only",
        "rho_projected",
        "linear_action_closure",
        "normal_projected_component_ratio",
        "complement_optimality",
        "alpha",
        "projection_denominator",
        "action_counts",
        "repeat_identical",
        "correction_sha256",
        "final_correction_sha256",
        "repeat_correction_sha256",
        "represented_action_sha256",
        "rhs_sha256",
        "local_correction_sha256",
        "local_action_sha256",
        "range_only_correction_sha256",
        "range_only_action_sha256",
        "range_correction_sha256",
        "range_action_sha256",
        "final_action_sha256",
        "final_residual_sha256",
        "final_range_correction_sha256",
        "final_range_action_sha256",
    }
    if not isinstance(value, Mapping) or not required <= set(value):
        return False
    action_counts = value["action_counts"]
    if not (
        isinstance(action_counts, Mapping)
        and action_counts.get("local_apply") == 1
        and action_counts.get("physical_outer_action") == 5
        and action_counts.get("range_apply") == 3
    ):
        return False
    quantities = (
        "rho_local_only",
        "rho_range_only",
        "rho_projected",
        "linear_action_closure",
        "normal_projected_component_ratio",
        "complement_optimality",
    )
    hash_fields = tuple(key for key in required if key.endswith("_sha256"))
    return bool(
        value.get("schema") == "task037.extra.h2b.m6b.projected-range-pc.v1"
        and type(value.get("iteration")) is int
        and _m6b_w2_sha_valid(value.get("residual_array_sha256"))
        and _m6b_w2_residual_artifact_valid(
            value.get("residual_artifact"), value.get("iteration")
        )
        and value.get("finite") is True
        and value.get("repeat_identical") is True
        and all(_m6b_w2_sha_valid(value.get(key)) for key in hash_fields)
        and all(
            _finite_number(value.get(key)) and float(value.get(key)) >= 0.0
            for key in quantities
        )
        and all(
            isinstance(value.get(key), list)
            and len(value[key]) == 2
            and all(_finite_number(item) for item in value[key])
            for key in ("alpha", "projection_denominator")
        )
    )


def _m6b_w2r_gate(measurements: Any) -> dict[str, Any]:
    checks = {
        "fixed_iterations": False,
        "residual_artifacts": False,
        "finite_deterministic": False,
        "range_authority": False,
        "linear_action_closure": False,
        "normal_projected_component": False,
        "complement_optimality": False,
        "projected_not_worse": False,
        "projected_rho_gate": False,
    }
    problems: list[str] = []
    expected_keys = {str(item) for item in M6B_W2_FIXED_RESIDUAL_ITERATIONS}
    if not isinstance(measurements, Mapping) or set(measurements) != expected_keys:
        problems.append("fixed_iterations")
        return {"pass": False, "checks": checks, "problems": problems}
    valid = all(
        _m6b_w2r_measurement_valid(measurements.get(key))
        for key in expected_keys
    )
    checks["fixed_iterations"] = bool(
        valid
        and all(
            measurements[key].get("iteration") == int(key)
            for key in expected_keys
        )
    )
    checks["residual_artifacts"] = bool(
        valid
        and all(
            measurements[key].get("residual_array_sha256")
            == M6B_W2_RESIDUAL_ARRAY_SHAS[key]
            for key in expected_keys
        )
    )
    checks["finite_deterministic"] = bool(
        valid
        and all(
            measurements[key].get("correction_sha256")
            == measurements[key].get("repeat_correction_sha256")
            == measurements[key].get("final_correction_sha256")
            for key in expected_keys
        )
    )
    checks["range_authority"] = bool(
        valid
        and all(
            abs(
                float(measurements[key].get("rho_range_only"))
                - M6B_W2_RANGE_RHO_AUTHORITY[key]
            )
            <= 1.0e-11
            for key in expected_keys
        )
    )
    checks["linear_action_closure"] = bool(
        valid
        and all(
            float(measurements[key].get("linear_action_closure")) <= 1.0e-11
            for key in expected_keys
        )
    )
    checks["normal_projected_component"] = bool(
        valid
        and all(
            float(measurements[key].get("normal_projected_component_ratio"))
            <= 1.0e-11
            for key in expected_keys
        )
    )
    checks["complement_optimality"] = bool(
        valid
        and all(
            float(measurements[key].get("complement_optimality")) <= 1.0e-11
            for key in expected_keys
        )
    )
    checks["projected_not_worse"] = bool(
        valid
        and all(
            float(measurements[key].get("rho_projected"))
            <= float(measurements[key].get("rho_range_only")) + 1.0e-12
            for key in expected_keys
        )
    )
    checks["projected_rho_gate"] = bool(
        valid
        and all(
            float(measurements[key].get("rho_projected")) <= 0.90
            for key in expected_keys
        )
    )
    problems.extend(key for key, passed in checks.items() if not passed)
    return {"pass": not problems, "checks": checks, "problems": problems}


def _m6b_w2_gate(measurements: Any) -> dict[str, Any]:
    checks = {
        "fixed_iterations": False,
        "residual_artifacts": False,
        "finite_deterministic": False,
        "range_authority": False,
        "linear_action_closure": False,
        "normal_projected_component": False,
        "composed_not_worse": False,
        "composed_rho_gate": False,
    }
    problems: list[str] = []
    expected_keys = {str(item) for item in M6B_W2_FIXED_RESIDUAL_ITERATIONS}
    if not isinstance(measurements, Mapping) or set(measurements) != expected_keys:
        problems.append("fixed_iterations")
        return {"pass": False, "checks": checks, "problems": problems}
    checks["fixed_iterations"] = True
    valid = all(_m6b_w2_measurement_valid(measurements[key]) for key in expected_keys)
    checks["fixed_iterations"] = bool(
        valid
        and all(
            measurements[key]["iteration"] == int(key)
            for key in expected_keys
        )
    )
    checks["residual_artifacts"] = bool(
        valid
        and all(
            measurements[key]["residual_array_sha256"]
            == M6B_W2_RESIDUAL_ARRAY_SHAS[key]
            and _m6b_w2_residual_artifact_valid(
                measurements[key]["residual_artifact"], int(key)
            )
            for key in expected_keys
        )
    )
    checks["finite_deterministic"] = bool(
        valid
        and all(
            measurements[key]["repeat_identical"] is True
            and measurements[key]["correction_sha256"]
            == measurements[key]["repeat_correction_sha256"]
            and measurements[key]["correction_sha256"]
            == measurements[key]["final_correction_sha256"]
            for key in expected_keys
        )
    )
    checks["range_authority"] = bool(
        valid
        and all(
            abs(
                float(measurements[key]["rho_range_only"])
                - M6B_W2_RANGE_RHO_AUTHORITY[key]
            )
            <= 1.0e-11
            for key in expected_keys
        )
    )
    checks["linear_action_closure"] = bool(
        valid
        and all(
            float(measurements[key]["linear_action_closure"]) <= 1.0e-11
            for key in expected_keys
        )
    )
    checks["normal_projected_component"] = bool(
        valid
        and all(
            float(measurements[key]["normal_projected_component_ratio"]) <= 1.0e-11
            for key in expected_keys
        )
    )
    checks["composed_not_worse"] = bool(
        valid
        and all(
            float(measurements[key]["rho_composed"])
            <= float(measurements[key]["rho_local_only"]) + 1.0e-12
            for key in expected_keys
        )
    )
    checks["composed_rho_gate"] = bool(
        valid
        and all(float(measurements[key]["rho_composed"]) <= 0.90 for key in expected_keys)
    )
    problems.extend(key for key, passed in checks.items() if not passed)
    return {"pass": not problems, "checks": checks, "problems": problems}


def _m6b_factor_audit_valid(value: Any, *, loaded: bool) -> bool:
    required = (
        "schema",
        "beta",
        "factor_order",
        "factor_count",
        "cell_count",
        "factor_payload_bytes",
        "retained_total_bytes",
        "retained_total_gate",
        "factor_reuse_count",
        "factor_copy_count",
        "full_dense_patch_matrix_retained",
        "pivots_retained",
        "mmap_readonly",
        "mmap_loaded",
        "max_live_patch_matrix_count",
        "max_live_lu_factor_count",
        "materialization_identity",
    )
    if not isinstance(value, Mapping) or any(key not in value for key in required):
        return False
    materialization = value["materialization_identity"]
    materialization_keys = {
        "global_matrix",
        "global_constraint_matrix",
        "patch_matrices",
        "per_cell_factor",
        "static_condensation",
        "trace_slab",
        "schur",
        "slab_factor",
    }
    return bool(
        value["schema"] == "task037.extra.h2b.m6b.shifted-lu-store.v1"
        and value["beta"] == M6B_BETA
        and value["factor_order"] == M6B_LOCAL_NLOC
        and value["factor_count"] == M6B_FACTOR_COUNT
        and value["cell_count"] == M6B_GLOBAL_CELLS
        and value["factor_payload_bytes"] == M6B_FACTOR_PAYLOAD_BYTES
        and type(value["retained_total_bytes"]) is int
        and value["retained_total_bytes"] >= M6B_FACTOR_PAYLOAD_BYTES
        and value["retained_total_bytes"] <= M6B_RETAINED_TOTAL_LIMIT_BYTES
        and value["retained_total_gate"] is True
        and value["factor_reuse_count"] == M6B_FACTOR_REUSE
        and value["factor_copy_count"] == 0
        and value["full_dense_patch_matrix_retained"] is False
        and value["pivots_retained"] is True
        and value["mmap_readonly"] is loaded
        and value["mmap_loaded"] is loaded
        and value["max_live_patch_matrix_count"] == 1
        and value["max_live_lu_factor_count"] == 1
        and isinstance(materialization, Mapping)
        and set(materialization) == materialization_keys
        and all(materialization[key] is False for key in materialization_keys)
    )


def _m6b_builder_factor_audit_valid(value: Any) -> bool:
    return _m6b_factor_audit_valid(value, loaded=False)


def _m6b_loaded_factor_audit_valid(value: Any) -> bool:
    return _m6b_factor_audit_valid(value, loaded=True)


def _m6b_lifecycle_valid(
    value: Any,
    *,
    online: bool,
    require_compiler_empty: bool | None = None,
) -> bool:
    required = (
        "return_code",
        "termination",
        "processes_gone",
        "peak_rss_bytes",
        "swap_bytes",
        "watchdog_rss_limit_bytes",
        "completion_rss_limit_bytes",
        "timeout_seconds",
    )
    if not isinstance(value, Mapping) or any(key not in value for key in required):
        return False
    if require_compiler_empty is None:
        require_compiler_empty = online
    compiler_ok = not require_compiler_empty or value.get("compiler_descendant_pids") == []
    limit = (
        M6B_ONLINE_COMPLETION_RSS_LIMIT_BYTES
        if online
        else M6B_WATCHDOG_RSS_LIMIT_BYTES
    )
    return bool(
        value["return_code"] == 0
        and value["termination"] is None
        and value["processes_gone"] is True
        and type(value["peak_rss_bytes"]) is int
        and value["peak_rss_bytes"] < limit
        and value["swap_bytes"] == 0
        and value["watchdog_rss_limit_bytes"] == M6B_WATCHDOG_RSS_LIMIT_BYTES
        and value["completion_rss_limit_bytes"]
        == M6B_ONLINE_COMPLETION_RSS_LIMIT_BYTES
        and _finite_number(value["timeout_seconds"])
        and float(value["timeout_seconds"]) > 0.0
        and compiler_ok
    )


def _m6b_screen_structure_valid(value: Any) -> bool:
    if not isinstance(value, Mapping) or set(value) != {
        str(item) for item in M6B_SCREEN_ITERATIONS
    }:
        return False
    return all(
        isinstance(value[key], Mapping)
        and _finite_number(value[key].get("true_relative_residual"))
        and float(value[key]["true_relative_residual"]) >= 0.0
        for key in value
    )


def _m6b_screen_valid(value: Any) -> bool:
    if not _m6b_screen_structure_valid(value):
        return False
    residuals = {
        key: float(value[key]["true_relative_residual"])
        for key in value
    }
    return bool(
        residuals["20"] <= M6B_SCREEN_RHO_LIMITS["20"]
        and residuals["100"] <= M6B_SCREEN_RHO_LIMITS["100"]
        and residuals["200"] <= M6B_SCREEN_RHO_LIMITS["200"]
        and residuals["150"] > 0.0
        and 1.0 - residuals["200"] / residuals["150"] >= M6B_IMPROVEMENT_LIMIT
    )


def _m6b_screen_metadata_valid(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    samples = value.get("samples")
    return bool(
        value.get("schema") == "task037.extra.h2b.m6b.screen.v1"
        and value.get("rows") == M6B_GLOBAL_ROWS
        and value.get("ksp_type") == "fgmres"
        and value.get("pc_side") == "right"
        and value.get("norm_type") == "unpreconditioned"
        and value.get("restart_set") == 20
        and value.get("max_it") == 200
        and value.get("max_it_actual") == 200
        and value.get("iterations") == 200
        and value.get("rtol") == 0.0
        and value.get("atol") == 0.0
        and value.get("fixed_screen") is True
        and type(value.get("converged_reason")) is int
        and type(value.get("operator_apply_count")) is int
        and value.get("operator_apply_count") > 0
        and type(value.get("pc_apply_count")) is int
        and value.get("pc_apply_count") > 0
        and value.get("sample_action_count") == len(M6B_SCREEN_ITERATIONS)
        and isinstance(samples, Mapping)
        and _m6b_screen_structure_valid(samples)
    )


def _m6b_w4_screen_metadata_valid(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    samples = value.get("samples")
    if not (
        value.get("schema") == "task037.extra.h2b.m6b.fbcgs-screen.v1"
        and value.get("rows") == M6B_GLOBAL_ROWS
        and value.get("ksp_type") == "fbcgs"
        and value.get("pc_side") == "right"
        and value.get("norm_type") == "unpreconditioned"
        and value.get("max_it") == M6B_W4_KSP_ITERATIONS[-1]
        and value.get("max_it_actual") == M6B_W4_KSP_ITERATIONS[-1]
        and value.get("iterations") == M6B_W4_KSP_ITERATIONS[-1]
        and value.get("rtol") == 0.0
        and value.get("atol") == 0.0
        and value.get("fixed_screen") is True
        and value.get("checkpoint_axis") == "pc_apply_budget"
        and value.get("monitor_solution_source") == "direct_ksp_solution_vec"
        and value.get("buildSolution_called") is False
        and value.get("monitor_extra_pc_applies") == 0
        and value.get("pc_apply_count") == 200
        and value.get("pc_apply_count_expected") == 200
        and value.get("pc_apply_count_closed") is True
        and value.get("breakdown") is False
        and type(value.get("converged_reason")) is int
        and isinstance(value.get("converged_reason_names"), list)
        and isinstance(value.get("breakdown_reason_names"), list)
        and "operator_apply_count" in value
        and (
            value.get("operator_apply_count") is None
            or (
                type(value.get("operator_apply_count")) is int
                and value.get("operator_apply_count") > 0
            )
        )
        and value.get("checkpoint_operator_apply_count") == len(
            M6B_W4_PC_APPLY_BUDGETS
        )
        and value.get("sample_action_count") == len(M6B_W4_PC_APPLY_BUDGETS)
        and isinstance(samples, Mapping)
        and set(samples) == {str(item) for item in M6B_W4_PC_APPLY_BUDGETS}
    ):
        return False
    for ksp_iteration, budget in M6B_W4_KSP_TO_PC_BUDGET.items():
        item = samples.get(str(budget))
        if not isinstance(item, Mapping):
            return False
        value = item.get("true_relative_residual")
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or float(value) < 0.0
            or item.get("iteration") != budget
            or item.get("ksp_iteration") != ksp_iteration
            or item.get("pc_apply_budget") != budget
            or item.get("checkpoint_axis") != "pc_apply_budget"
            or item.get("iteration_label_is_pc_apply_budget") is not True
            or item.get("pc_apply_count") != budget
            or item.get("reported_residual_is_diagnostic_only") is not True
            or not isinstance(item.get("artifacts"), Mapping)
        ):
            return False
    return True


def _m6b_w5_screen_metadata_valid(
    value: Any,
    *,
    expected_schema: str = M6B_W5_CORE_SCHEMA,
    expected_action_count: int = 204,
    expected_initial_action_count: int = 0,
    expected_cycle: str = "fixed_one_200_step_cycle",
) -> bool:
    required = {
        "schema",
        "rows",
        "solver",
        "petsc_ksp_used",
        "side",
        "two_pass_mgs",
        "cycle",
        "max_steps",
        "iterations",
        "checkpoint_iterations",
        "true_residual_authority",
        "estimated_residual_is_diagnostic_only",
        "happy_breakdown",
        "samples",
        "numeric_gate",
        "core_audit",
        "scratch",
        "action_count",
        "pc_count",
        "read_write_counts",
    }
    if not isinstance(value, Mapping) or not required.issubset(value):
        return False
    if not (
        value["schema"] == expected_schema
        and value["rows"] == M6B_GLOBAL_ROWS
        and value["solver"] == "disk_backed_flexible_gmres"
        and value["petsc_ksp_used"] is False
        and value["side"] == "right"
        and value["two_pass_mgs"] is True
        and value["cycle"] == expected_cycle
        and value["max_steps"] == 200
        and value["iterations"] == 200
        and value["checkpoint_iterations"] == [20, 100, 150, 200]
        and value["true_residual_authority"] == "rhs-outer_action"
        and value["estimated_residual_is_diagnostic_only"] is True
        and value["happy_breakdown"] is False
    ):
        return False
    samples = value["samples"]
    if not isinstance(samples, Mapping) or set(samples) != {
        "20",
        "100",
        "150",
        "200",
    }:
        return False
    for key in samples:
        item = samples[key]
        if not isinstance(item, Mapping) or not {
            "iteration",
            "true_relative_residual",
            "estimated_residual_norm",
            "estimated_residual_is_diagnostic_only",
            "artifacts",
        }.issubset(item):
            return False
        if not (
            item["iteration"] == int(key)
            and _finite_number(item["true_relative_residual"])
            and float(item["true_relative_residual"]) >= 0.0
            and _finite_number(item["estimated_residual_norm"])
            and item["estimated_residual_is_diagnostic_only"] is True
        ):
            return False
        artifacts = item["artifacts"]
        if not isinstance(artifacts, Mapping) or set(artifacts) != {
            "solution",
            "outer_action",
            "residual",
            "rhs",
        }:
            return False
        for artifact in artifacts.values():
            if not isinstance(artifact, Mapping) or not {
                "path",
                "bytes",
                "sha256",
                "array_sha256",
            }.issubset(artifact):
                return False
    core = value["core_audit"]
    if not isinstance(core, Mapping) or not {
        "algorithm",
        "rows",
        "dtype",
        "action_count",
        "pc_count",
        "initial_action_count",
        "orthogonalization_passes",
        "happy_breakdown",
        "retained_full_vector_count",
        "iterations",
        "checkpoint_set_complete",
        "checkpoint_count",
        "bounded_full_vector_bytes",
        "bounded_full_vector_gate",
        "mmap",
        "basis_in_memory",
        "scratch_bytes",
        "v_basis",
        "z_basis",
    }.issubset(core):
        return False
    if not (
        core["algorithm"] == "right_flexible_gmres"
        and core["rows"] == M6B_GLOBAL_ROWS
        and core["dtype"] == "complex128"
        and core["action_count"] == expected_action_count
        and core["pc_count"] == 200
        and core["initial_action_count"] == expected_initial_action_count
        and core["orthogonalization_passes"] == 2
        and core["happy_breakdown"] is False
        and core["retained_full_vector_count"] == 1
        and core["iterations"] == 200
        and core["checkpoint_set_complete"] is True
        and core["checkpoint_count"] == 4
        and core["bounded_full_vector_bytes"] <= M6B_W5_FULL_VECTOR_BUFFER_LIMIT_BYTES
        and core["bounded_full_vector_gate"] is True
        and core["mmap"] is False
        and core["basis_in_memory"] is False
        and core["scratch_bytes"] == M6B_W5_SCRATCH_BYTES
    ):
        return False
    for name, capacity, written in (
        ("v_basis", 201, 201),
        ("z_basis", 200, 200),
    ):
        basis = core[name]
        if not isinstance(basis, Mapping) or not {
            "rows",
            "dtype",
            "capacity",
            "written_count",
            "read_count",
            "write_count",
            "allocated_bytes",
            "mmap",
        }.issubset(basis):
            return False
        if not (
            basis["rows"] == M6B_GLOBAL_ROWS
            and basis["dtype"] == "complex128"
            and basis["capacity"] == capacity
            and basis["written_count"] == written
            and basis["read_count"] == (40200 if name == "v_basis" else 470)
            and basis["write_count"] == written
            and basis["allocated_bytes"]
            == (558_947_232 if name == "v_basis" else 556_166_400)
            and basis["mmap"] is False
        ):
            return False
    scratch = value["scratch"]
    return bool(
        isinstance(scratch, Mapping)
        and scratch.get("bytes") == M6B_W5_SCRATCH_BYTES
        and scratch.get("mmap") is False
        and scratch.get("basis_in_memory") is False
        and isinstance(value["numeric_gate"], Mapping)
        and type(value["action_count"]) is int
        and value["action_count"] == expected_action_count
        and type(value["pc_count"]) is int
        and value["pc_count"] == 200
        and isinstance(value["read_write_counts"], Mapping)
        and isinstance(value["read_write_counts"].get("v_basis"), Mapping)
        and isinstance(value["read_write_counts"].get("z_basis"), Mapping)
        and value["read_write_counts"]["v_basis"].get("read_count") == 40200
        and value["read_write_counts"]["v_basis"].get("write_count") == 201
        and value["read_write_counts"]["z_basis"].get("read_count") == 470
        and value["read_write_counts"]["z_basis"].get("write_count") == 200
    )


def _m6b_w7_s1_screen_metadata_valid(value: Any) -> bool:
    if not _m6b_w5_screen_metadata_valid(
        value,
        expected_schema=M6B_W7_S1_CORE_SCHEMA,
        expected_action_count=205,
        expected_initial_action_count=1,
        expected_cycle="fixed_one_200_step_restart_cycle",
    ):
        return False
    if not (
        value.get("checkpoint_axis") == "local_cycle_iteration"
        and value.get("cumulative_checkpoint_iterations")
        == list(M6B_W7_S1_CUMULATIVE_ITERATIONS)
        and value.get("initial_solution_provided") is True
        and isinstance(value.get("continuation_authority"), Mapping)
    ):
        return False
    samples = value["samples"]
    return all(
        samples[str(local)].get("local_iteration") == local
        and samples[str(local)].get("cumulative_iteration") == cumulative
        for local, cumulative in zip(
            M6B_W7_S1_LOCAL_ITERATIONS, M6B_W7_S1_CUMULATIVE_ITERATIONS
        )
    )


def _m6b_builder_summary_valid(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    sample = value.get("sample_patch_action_closure")
    class_audit = value.get("class_block_audit")
    cache = value.get("cache")
    form = value.get("form")
    shared_kernel = value.get("shared_volume_kernel")
    return bool(
        isinstance(sample, Mapping)
        and set(sample) == {"0", "42", "83"}
        and all(
            _finite_number(sample[key])
            and 0.0 <= float(sample[key]) <= 1.0e-11
            for key in sample
        )
        and isinstance(class_audit, Mapping)
        and class_audit.get("class_count") == 24
        and class_audit.get("factor_count") == 24
        and class_audit.get("reconstruction_count") == 24
        and class_audit.get("fresh_B_beta_class_count") == 24
        and class_audit.get("fresh_B_beta_matrix_count") == 24
        and class_audit.get("operator_identity") == M6B_SHIFTED_OPERATOR
        and class_audit.get("numeric_matrix_source")
        == "fresh_transformed_B_beta_class_block"
        and class_audit.get("r2_numeric_store_used_for_blocks") is False
        and class_audit.get("global_matrix_materialized") is False
        and isinstance(cache, Mapping)
        and all(key in cache for key in ("stage", "before", "after", "unchanged"))
        and cache["stage"] == cache["before"] == cache["after"]
        and cache["unchanged"] is True
        and _m6b_shared_kernel_valid(shared_kernel, phase="builder")
        and _m6b_form_record_bound(
            form,
            shared_kernel,
            role="shifted_volume",
            beta=M6B_BETA,
            code_state="hit_no_new_decl_impl",
            shared_phase="stage",
        )
        and _m6b_material_tag_coverage_valid(
            value.get("material_tag_coverage"), owned_cells=M6B_GLOBAL_CELLS
        )
    )


def _m6b_pc_audit_valid(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    materialization = value.get("materialization_identity")
    required_materialization = {
        "global_matrix",
        "global_constraint_matrix",
        "patch_matrices",
        "per_cell_factor",
        "static_condensation",
        "trace_slab",
        "schur",
        "slab_factor",
    }
    closure = value.get("partition_of_unity_closure_error")
    return bool(
        value.get("beta") == M6B_BETA
        and value.get("unique_factor_count") == M6B_FACTOR_COUNT
        and value.get("solve_count_per_apply") == M6B_FACTOR_COUNT
        and value.get("factor_reuse_count") == M6B_FACTOR_REUSE
        and value.get("factor_reuse_exercised") == M6B_FACTOR_REUSE
        and value.get("rhs_count") == M6B_GLOBAL_CELLS
        and value.get("factor_copy_count") == 0
        and value.get("per_cell_solution_retained") is False
        and value.get("fine_space") == "uncondensed_fullspace"
        and _finite_number(closure)
        and 0.0 <= float(closure) <= 1.0e-14
        and isinstance(materialization, Mapping)
        and set(materialization) == required_materialization
        and all(materialization[key] is False for key in required_materialization)
    )


def _m6b_phase_source_identity(
    summaries: Mapping[str, Any],
) -> dict[str, Any]:
    expected = ("stage", "builder", "online", "watchdog")
    if set(summaries) != set(expected):
        return {
            "pass": False,
            "source_commit_full_sha": None,
            "phase_names": list(expected),
            "all_tracked_source_clean": False,
        }
    commits: set[str] = set()
    clean = True
    for name in expected:
        summary = summaries[name]
        if not isinstance(summary, Mapping):
            clean = False
            continue
        start = summary.get("source_at_start")
        end = summary.get("source_at_end")
        if not isinstance(start, Mapping) or not isinstance(end, Mapping):
            clean = False
            continue
        if start.get("source_commit_full_sha") != end.get("source_commit_full_sha"):
            clean = False
        if start.get("tracked_source_dirty") is not False or end.get(
            "tracked_source_dirty"
        ) is not False:
            clean = False
        commit = start.get("source_commit_full_sha")
        if isinstance(commit, str):
            commits.add(commit)
        else:
            clean = False
    same = len(commits) == 1
    commit = next(iter(commits)) if same else None
    return {
        "pass": bool(same and clean),
        "source_commit_full_sha": commit,
        "phase_names": list(expected),
        "all_tracked_source_clean": bool(clean),
    }


def _m6b_check_payload(value: Any) -> dict[str, Any]:
    """Check a worker-shaped compact mapping without defaulting missing keys."""

    checks = {
        "schema": False,
        "scope": False,
        "p6_identity": False,
        "factor_audit": False,
        "builder_factor_audit": False,
        "screen": False,
        "stage_lifecycle": False,
        "online_lifecycle": False,
        "architecture": False,
        "source_pair": False,
        "runtime_identity": False,
        "cache_identity": False,
        "pc_repeat": False,
        "phase_source_identity": False,
        "pc_audit": False,
        "shared_volume_kernel": False,
        "material_tag_coverage": False,
    }
    problems: list[str] = []
    if not isinstance(value, Mapping):
        return {"pass": False, "checks": checks, "problems": ["raw_mapping"]}
    checks["schema"] = value.get("schema") == M6B_WORKER_SCHEMA
    checks["scope"] = value.get("scope") == _m6b_scope(phase="mpi1")
    checks["p6_identity"] = value.get("p6") == {
        "global_cells": M6B_GLOBAL_CELLS,
        "local_cells": M6B_GLOBAL_CELLS,
        "local_nloc": M6B_LOCAL_NLOC,
        "global_rows": M6B_GLOBAL_ROWS,
        "constraint_count": M6B_CONSTRAINTS,
    }
    factor = value.get("factor_store")
    checks["factor_audit"] = _m6b_loaded_factor_audit_valid(factor)
    checks["builder_factor_audit"] = _m6b_builder_factor_audit_valid(
        value.get("builder_factor_audit")
    )
    screen = value.get("screen")
    screen_metadata = value.get("screen_metadata")
    checks["screen"] = bool(
        _m6b_screen_valid(screen)
        and _m6b_screen_metadata_valid(screen_metadata)
        and screen_metadata.get("samples") == screen
    ) if isinstance(screen_metadata, Mapping) else False
    stage_lifecycle = value.get("stage")
    online_lifecycle = value.get("online")
    checks["stage_lifecycle"] = bool(
        _m6b_lifecycle_valid(stage_lifecycle, online=False)
        and stage_lifecycle["timeout_seconds"] == M6B_STAGE_TIMEOUT_SECONDS
    ) if isinstance(stage_lifecycle, Mapping) else False
    checks["online_lifecycle"] = bool(
        _m6b_lifecycle_valid(online_lifecycle, online=True)
        and online_lifecycle["timeout_seconds"] == M6B_ONLINE_TIMEOUT_SECONDS
    ) if isinstance(online_lifecycle, Mapping) else False
    architecture = value.get("architecture")
    required_architecture = (
        "fine_space",
        "global_matrix",
        "augmented_matrix",
        "static_condensation",
        "trace_slab_pc",
        "explicit_C_materialized_count",
        "explicit_D_materialized_count",
        "dtn",
        "pde",
    )
    checks["architecture"] = bool(
        isinstance(architecture, Mapping)
        and set(architecture) == set(required_architecture)
        and all(key in architecture for key in required_architecture)
        and architecture["fine_space"] == "uncondensed_fullspace"
        and all(
            architecture[key] is False
            for key in (
                "global_matrix",
                "augmented_matrix",
                "static_condensation",
                "trace_slab_pc",
                "pde",
            )
        )
        and architecture["dtn"] is True
        and architecture["explicit_C_materialized_count"] == 0
        and architecture["explicit_D_materialized_count"] == 0
    )
    start = value.get("source_at_start")
    end = value.get("source_at_end")
    checks["source_pair"] = bool(
        isinstance(start, Mapping)
        and isinstance(end, Mapping)
        and start.get("source_commit_full_sha")
        and start.get("source_commit_full_sha") == end.get("source_commit_full_sha")
        and start.get("tracked_source_dirty") is False
        and end.get("tracked_source_dirty") is False
    )
    phase_identity = value.get("phase_source_identity")
    checks["phase_source_identity"] = bool(
        isinstance(phase_identity, Mapping)
        and phase_identity.get("pass") is True
        and phase_identity.get("phase_names")
        == ["stage", "builder", "online", "watchdog"]
        and phase_identity.get("all_tracked_source_clean") is True
        and isinstance(phase_identity.get("source_commit_full_sha"), str)
        and isinstance(start, Mapping)
        and isinstance(end, Mapping)
        and phase_identity.get("source_commit_full_sha") == start.get(
            "source_commit_full_sha"
        )
        and phase_identity.get("source_commit_full_sha") == end.get(
            "source_commit_full_sha"
        )
    )
    try:
        import benchmarks.run_task037_extra_h2b as h2b

        runtime = value["runtime_identity"]
        checks["runtime_identity"] = bool(
            h2b._runtime_valid(runtime)
            and isinstance(runtime.get("compiler"), Mapping)
            and runtime.get("mpi_size") == 1
        )
    except (ImportError, KeyError, TypeError, AttributeError):
        checks["runtime_identity"] = False
    cache = value.get("cache")
    checks["cache_identity"] = bool(
        isinstance(cache, Mapping)
        and all(
            key in cache for key in ("stage", "before", "after", "final", "unchanged")
        )
        and cache["stage"] == cache["before"] == cache["after"] == cache["final"]
        and cache["unchanged"] is True
    )
    repeat = value.get("pc_repeat")
    required_probe_hashes = {
        "rhs_sha256",
        "correction0_sha256",
        "action_sha256",
        "correction_sha256",
        "residual_sha256",
    }
    checks["pc_repeat"] = bool(
        isinstance(repeat, Mapping)
        and repeat.get("identical") is True
        and isinstance(repeat.get("first"), Mapping)
        and isinstance(repeat.get("second"), Mapping)
        and repeat["first"].get("hashes") == repeat["second"].get("hashes")
        and set(repeat["first"].get("hashes", {})) == required_probe_hashes
        and all(
            _finite_number(repeat[side].get("wall_seconds"))
            and repeat[side].get("finite") is True
            and repeat[side].get("exact_shifted_action_count") == 1
            and _finite_number(repeat[side].get("partition_of_unity_closure_error"))
            and float(repeat[side]["partition_of_unity_closure_error"]) >= 0.0
            and float(repeat[side]["partition_of_unity_closure_error"]) <= 1.0e-14
            for side in ("first", "second")
        )
    )
    online_measurement = value.get("online_measurement")
    shared_kernel = (
        online_measurement.get("shared_volume_kernel")
        if isinstance(online_measurement, Mapping)
        else None
    )
    online_form = (
        online_measurement.get("form")
        if isinstance(online_measurement, Mapping)
        else None
    )
    checks["shared_volume_kernel"] = bool(
        _m6b_shared_kernel_valid(shared_kernel, phase="mpi1")
        and isinstance(online_form, Mapping)
        and _m6b_form_records_bound(
            online_form.get("outer_volume"),
            online_form.get("shifted_volume"),
            shared_kernel,
            phase="mpi1",
        )
    )
    checks["material_tag_coverage"] = _m6b_material_tag_coverage_valid(
        online_measurement.get("material_tag_coverage")
        if isinstance(online_measurement, Mapping)
        else None,
        owned_cells=M6B_GLOBAL_CELLS,
    )
    checks["pc_audit"] = bool(
        isinstance(online_measurement, Mapping)
        and _m6b_pc_audit_valid(online_measurement.get("pc_audit"))
    )
    problems.extend(name for name, passed in checks.items() if not passed)
    return {
        "pass": not problems,
        "checks": checks,
        "problems": problems,
        "scope": _m6b_scope(phase="mpi1"),
        "predicted_live_set": _predicted_live_set(),
    }


def _m6b_emit(stream: Any, phase: str, event: str, started: float, **extra: Any) -> None:
    expected = {
        "stage": M6B_STAGE_EVENTS,
        "builder": M6B_BUILDER_EVENTS,
        "mpi1": M6B_ONLINE_EVENTS,
    }[phase]
    if event not in expected:
        raise ValueError(f"M6B unknown progress event: {event}")
    payload = {
        "schema": f"{M6B_SCHEMA}.progress.v1",
        "phase": phase,
        "event": event,
        "elapsed_wall_seconds": float(__import__("time").perf_counter() - started),
        **extra,
    }
    stream.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    stream.flush()
    print(json.dumps(payload, sort_keys=True), flush=True)


def _m6b_w1_cache_deltas(
    target_before: Mapping[str, Any],
    target_after_forward: Mapping[str, Any],
    target_after_adjoint: Mapping[str, Any],
    target_after_surface: Mapping[str, Any],
    target_final: Mapping[str, Any],
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """Classify W1 target-cache content changes between fixed lifecycle points."""

    def delta(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
        before_by_path = {
            item["path"]: {
                "path": item["path"],
                "bytes": int(item["bytes"]),
                "sha256": item["sha256"],
            }
            for item in before["entries"]
        }
        after_by_path = {
            item["path"]: {
                "path": item["path"],
                "bytes": int(item["bytes"]),
                "sha256": item["sha256"],
            }
            for item in after["entries"]
        }
        added = [after_by_path[path] for path in sorted(after_by_path.keys() - before_by_path.keys())]
        removed = [before_by_path[path] for path in sorted(before_by_path.keys() - after_by_path.keys())]
        changed = [
            {
                "path": path,
                "before": before_by_path[path],
                "after": after_by_path[path],
            }
            for path in sorted(before_by_path.keys() & after_by_path.keys())
            if before_by_path[path] != after_by_path[path]
        ]
        return {"added": added, "removed": removed, "changed": changed}

    return {
        "forward_delta": delta(target_before, target_after_forward),
        "adjoint_staging_delta": delta(
            target_after_forward, target_after_adjoint
        ),
        "surface_delta": delta(target_after_adjoint, target_after_surface),
        "final_delta": delta(target_after_surface, target_final),
    }


def _run_m6b_w1_builder(run_dir: Path, jit_cache_source: Path) -> int:
    """Build the W1 sparse ``Z``/``A Z`` carrier without running a screen."""

    import gc
    import shutil
    import time
    from types import SimpleNamespace

    import numpy as np
    from mpi4py import MPI
    import ufl

    h2b = __import__("benchmarks.run_task037_extra_h2b", fromlist=["*"])
    m6a = __import__("benchmarks.run_task037_extra_m6", fromlist=["*"])
    from benchmarks.run_workstation_iterative import _fixed_floquet_hat_basis
    from src.solvers.hcurl_fullspace_dtn import (
        build_fullspace_dtn_action,
        build_fullspace_dtn_carrier_from_surface,
    )
    from src.solvers.hcurl_h2b_m6b_shifted_patch_pc import (
        build_m6b_outer_mat,
        build_m6b_volume_form,
    )
    from src.solvers.hcurl_m6b_sparse_range import (
        M6B_W1_W0_AZ_COLUMN_SHA256_AGGREGATE,
        M6B_W1_W0_BASIS_MANIFEST_SHA256,
        M6B_W1_W0_ORACLE_EXECUTION_SOURCE_SHA,
        M6B_W1_W0_ORACLE_OUTPUT_SHA256,
        M6B_W1_W0_RESIDUAL_SOURCE_SHA,
        SparseM6BRangeCarrier,
        basis_manifest_from_vectors,
        load_sparse_m6b_range_carrier,
        validate_w0_authority,
    )
    from src.solvers.hcurl_rank_one_mpc_action import build_task037_extra_h1r2_mpc_action

    run_dir = Path(run_dir).resolve()
    jit_cache_source = Path(jit_cache_source).resolve()
    if run_dir.exists():
        raise FileExistsError(f"W1 builder refuses existing directory: {run_dir}")
    if not jit_cache_source.is_dir():
        raise FileNotFoundError(f"W1 JIT cache source is missing: {jit_cache_source}")
    if MPI.COMM_WORLD.size != 1:
        raise RuntimeError("W1 sparse range builder is fixed to MPI1")
    run_dir.mkdir(parents=True)
    cache_dir = run_dir / "jit_cache"
    shutil.copytree(jit_cache_source, cache_dir)
    started = time.perf_counter()
    progress_path = run_dir / "w1_builder_progress.jsonl"

    def emit(event: str, **extra: Any) -> None:
        payload = {
            "schema": f"{M6B_W1_SCHEMA}.progress.v1",
            "phase": "w1_builder",
            "event": event,
            "elapsed_wall_seconds": float(time.perf_counter() - started),
            **extra,
        }
        with progress_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
            stream.flush()
        print(json.dumps(payload, sort_keys=True), flush=True)

    def cache_record(path: Path) -> dict[str, Any]:
        entries = h2b._cache_snapshot(path)
        content_entries = [
            {
                "path": item["path"],
                "bytes": item["bytes"],
                "sha256": item["sha256"],
            }
            for item in entries
        ]
        inventory_sha = hashlib.sha256(
            h2b._canonical_json({"entries": content_entries})
        ).hexdigest()
        return {"entries": content_entries, "inventory_sha256": inventory_sha}

    emit("cache_ready", source=str(jit_cache_source))
    source_cache_before = cache_record(jit_cache_source)
    target_cache_before = cache_record(cache_dir)
    if target_cache_before["inventory_sha256"] != source_cache_before["inventory_sha256"]:
        raise ValueError("W1 copied JIT cache differs from source")
    cfg = mesh_data = function_space = floquet = None
    physical_action = adjoint_physical_action = dtn_action = outer_mat = outer_context = None
    surface_assemblers = None
    volume_ufl = adjoint_ufl = epsilon = abs_epsilon = beta = None
    template = None
    try:
        cfg, mesh_data, function_space, floquet, modes = m6a._production_objects(
            run_dir, mesh_name="m6b_w1_mesh"
        )
        physical_ufl, epsilon, abs_epsilon, beta, tag_coverage = build_m6b_volume_form(
            function_space, mesh_data, cfg, beta=0.0
        )
        volume_ufl = physical_ufl
        physical_action = build_task037_extra_h1r2_mpc_action(
            physical_ufl,
            floquet.mpc,
            task037_extra_h1r2=True,
            jit_options=h2b._expected_jit_options(cache_dir),
        )
        target_cache_after_forward = cache_record(cache_dir)
        source_cache_after_forward = cache_record(jit_cache_source)
        if (
            target_cache_after_forward["inventory_sha256"]
            != target_cache_before["inventory_sha256"]
            or source_cache_after_forward["inventory_sha256"]
            != source_cache_before["inventory_sha256"]
        ):
            raise ValueError("W1 physical forward action changed the JIT cache")
        adjoint_ufl = ufl.adjoint(physical_ufl)
        adjoint_physical_action = build_task037_extra_h1r2_mpc_action(
            adjoint_ufl,
            floquet.mpc,
            task037_extra_h1r2=True,
            jit_options=h2b._expected_jit_options(cache_dir),
        )
        target_cache_after_adjoint = cache_record(cache_dir)
        source_cache_after_adjoint = cache_record(jit_cache_source)
        if source_cache_after_adjoint["inventory_sha256"] != source_cache_before[
            "inventory_sha256"
        ]:
            raise ValueError("W1 adjoint action changed the source JIT cache")
        surface_assemblers = m6a._surface_assemblers(
            function_space, mesh_data, cfg, modes, cache_dir
        )
        target_cache_after_surface = cache_record(cache_dir)
        source_cache_after_surface = cache_record(jit_cache_source)
        if (
            target_cache_after_surface["inventory_sha256"]
            != target_cache_after_adjoint["inventory_sha256"]
            or source_cache_after_surface["inventory_sha256"]
            != source_cache_before["inventory_sha256"]
        ):
            raise ValueError("W1 surface forms changed the frozen JIT cache")
        emit(
            "forms_ready",
            cache_inventory_sha256=target_cache_after_surface["inventory_sha256"],
            adjoint_form_staged=True,
        )
        carrier = build_fullspace_dtn_carrier_from_surface(
            modes,
            surface_assemblers,
            floquet.mpc,
            cfg,
            expected_mode_count=80,
        )
        dtn_action = build_fullspace_dtn_action(carrier, comm=MPI.COMM_WORLD)
        outer_mat, outer_context = build_m6b_outer_mat(
            physical_action,
            dtn_action,
            owned_rows=M6B_GLOBAL_ROWS,
            global_rows=M6B_GLOBAL_ROWS,
            comm=MPI.COMM_WORLD,
            volume_hermitian_action=adjoint_physical_action,
        )
        template = outer_mat.createVecRight()
        ownership = tuple(int(value) for value in template.getOwnershipRange())
        local_rows = ownership[1] - ownership[0]

        def apply_local(values: np.ndarray, *, hermitian: bool = False) -> np.ndarray:
            values = np.asarray(values, dtype=np.complex128)
            if (
                values.ndim != 1
                or values.size != local_rows
                or not np.all(np.isfinite(values))
            ):
                raise ValueError("W1 outer probe has an invalid owned layout")
            source = template.duplicate()
            result = template.duplicate()
            try:
                np.copyto(source.getArray(), values)
                if hermitian:
                    outer_context.apply_hermitian(source, result)
                else:
                    outer_mat.mult(source, result)
                return np.array(
                    result.getArray(readonly=True),
                    dtype=np.complex128,
                    copy=True,
                )
            finally:
                result.destroy()
                source.destroy()

        probe_index = np.arange(local_rows, dtype=np.float64)
        x_values = 0.125 + 1.0e-6 * probe_index + 1j * (
            0.25 - 2.0e-6 * probe_index
        )
        y_values = -0.375 + 1.5e-6 * probe_index + 1j * (
            0.5 - 1.0e-6 * probe_index
        )
        x_before = x_values.copy()
        y_before = y_values.copy()
        forward_values = apply_local(x_values)
        adjoint_values = apply_local(y_values, hermitian=True)
        adjoint_repeat = apply_local(y_values, hermitian=True)
        lhs = np.vdot(forward_values, y_values)
        rhs = np.vdot(x_values, adjoint_values)
        inner_product_defect = float(
            abs(lhs - rhs) / max(abs(lhs), abs(rhs), np.finfo(float).tiny)
        )
        adjoint_finite = bool(
            np.all(np.isfinite(forward_values))
            and np.all(np.isfinite(adjoint_values))
            and np.all(np.isfinite(adjoint_repeat))
        )
        adjoint_repeat_equal = bool(np.array_equal(adjoint_values, adjoint_repeat))
        probe_sources_unchanged = bool(
            np.array_equal(x_values, x_before)
            and np.array_equal(y_values, y_before)
        )
        adjoint_identity = {
            "schema": "task037.extra.m6b.w1.adjoint-identity.v1",
            "relative_inner_product_defect": inner_product_defect,
            "limit": 1.0e-11,
            "finite": adjoint_finite,
            "repeat_equal": adjoint_repeat_equal,
            "source_unchanged": probe_sources_unchanged,
            "forward_action_count": 1,
            "adjoint_action_count": 1,
            "adjoint_repeat_action_count": 1,
            "adjoint_total_action_count": 2,
            "outer_forward_apply_count": int(outer_context.apply_count),
            "outer_adjoint_apply_count": int(
                outer_context.audit["hermitian_apply_count"]
            ),
            "volume_forward_action_count": int(physical_action.audit["apply_count"]),
            "volume_adjoint_action_count": int(
                adjoint_physical_action.audit["apply_count"]
            ),
            "lhs_abs": float(abs(lhs)),
            "rhs_abs": float(abs(rhs)),
            "lhs_real": float(lhs.real),
            "lhs_imag": float(lhs.imag),
            "rhs_real": float(rhs.real),
            "rhs_imag": float(rhs.imag),
            "repeat_max_abs_diff": float(
                np.max(np.abs(adjoint_values - adjoint_repeat))
            ),
        }
        if not (
            adjoint_finite
            and adjoint_repeat_equal
            and probe_sources_unchanged
            and inner_product_defect <= adjoint_identity["limit"]
        ):
            raise ValueError("W1 full-space adjoint identity Gate failed")
        emit(
            "adjoint_identity_ready",
            relative_inner_product_defect=inner_product_defect,
            forward_action_count=1,
            adjoint_action_count=1,
            repeat_action_count=1,
        )
        del (
            probe_index,
            x_values,
            y_values,
            x_before,
            y_before,
            forward_values,
            adjoint_values,
            adjoint_repeat,
        )

        def basis_progress(completed: int, total: int) -> None:
            if completed % 5 == 0 or completed == total:
                emit("basis_progress", completed=completed, total=total)

        basis = tuple(
            _fixed_floquet_hat_basis(
                SimpleNamespace(cfg=cfg, V=function_space, floquet_data=floquet),
                outer_mat,
                coarse_slabs=24,
                progress=basis_progress,
            )
        )
        if len(basis) != 75:
            raise ValueError("W1 fixed basis rank is not 75")
        basis_manifest = basis_manifest_from_vectors(basis)
        basis_manifest_sha256 = hashlib.sha256(
            json.dumps(
                basis_manifest,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        if basis_manifest_sha256 != M6B_W1_W0_BASIS_MANIFEST_SHA256:
            raise ValueError("W1 basis manifest differs from frozen W0 authority")
        emit("basis_ready", completed=75, total=75, basis_manifest_sha256=basis_manifest_sha256)

        action_count = [0]

        def apply_column(vector: Any) -> np.ndarray:
            local = np.zeros(local_rows, dtype=np.complex128)
            rows = np.asarray(vector.indices, dtype=np.int64)
            start, end = ownership
            if rows.size and (rows.min() < start or rows.max() >= end):
                raise ValueError("W1 fixed basis row is outside ownership")
            local[rows - start] = np.asarray(vector.values, dtype=np.complex128)
            represented = apply_local(local)
            action_count[0] += 1
            if action_count[0] % 5 == 0 or action_count[0] == 75:
                emit("az_progress", completed=action_count[0], total=75)
            return represented

        def apply_hermitian_column(values: np.ndarray) -> np.ndarray:
            return apply_local(values, hermitian=True)

        identity = {
            "source_sha": h2b._light_source()["source_commit_full_sha"],
            "operator_identity": "A=Kcurl-k0^2*M_epsilon+A_DtN",
            "basis_manifest_sha256": basis_manifest_sha256,
            "basis_manifest": basis_manifest,
            "basis_helper": "benchmarks.run_workstation_iterative._fixed_floquet_hat_basis",
            "coarse_slabs": 24,
            "w0_az_column_sha256_aggregate": M6B_W1_W0_AZ_COLUMN_SHA256_AGGREGATE,
            "w0_oracle_output_sha256": M6B_W1_W0_ORACLE_OUTPUT_SHA256,
            "w0_residual_source_sha": M6B_W1_W0_RESIDUAL_SOURCE_SHA,
            "w0_oracle_execution_source_sha": M6B_W1_W0_ORACLE_EXECUTION_SOURCE_SHA,
            "fine_space": "uncondensed_fullspace",
            "global_matrix": False,
            "static_condensation": False,
            "trace_slab_pc": False,
        }
        carrier = SparseM6BRangeCarrier.from_action(
            basis,
            apply_column,
            hermitian_action=apply_hermitian_column,
            global_rows=M6B_GLOBAL_ROWS,
            ownership_range=ownership,
            comm=MPI.COMM_WORLD,
            identity=identity,
        )
        validate_w0_authority(identity, carrier.audit["az_column_sha256_aggregate"])
        emit(
            "az_ready",
            completed=75,
            total=75,
            az_column_sha256_aggregate=carrier.audit["az_column_sha256_aggregate"],
        )
        manifest_path = carrier.save(run_dir / "sparse_range_store")
        del carrier
        gc.collect()
        loaded = load_sparse_m6b_range_carrier(
            manifest_path,
            hermitian_action=apply_hermitian_column,
        )
        audit = loaded.audit
        final_cache = cache_record(cache_dir)
        source_cache_after = cache_record(jit_cache_source)
        if (
            final_cache["inventory_sha256"]
            != target_cache_after_surface["inventory_sha256"]
            or source_cache_after["inventory_sha256"]
            != source_cache_before["inventory_sha256"]
        ):
            raise ValueError("W1 JIT cache changed after form construction")
        cache_deltas = _m6b_w1_cache_deltas(
            target_cache_before,
            target_cache_after_forward,
            target_cache_after_adjoint,
            target_cache_after_surface,
            final_cache,
        )
        emit("store_ready", manifest=str(manifest_path))
        predicted = int(
            M6B_W1_BASE_PREDICTED_LIVE_SET_BYTES
            + audit["retained_total_bytes"]
            + audit["bounded_work_bytes"]
            + int(adjoint_physical_action.audit["retained_numeric_payload_global_max_bytes"])
            + int(adjoint_physical_action.audit["per_apply_bounded_temporary_bytes"])
        )
        if predicted > M6B_W1_PREDICTED_LIVE_SET_LIMIT_BYTES:
            raise ValueError("W1 derived live-set prediction exceeds fixed limit")
        full_vector_bytes = int(local_rows * np.dtype(np.complex128).itemsize)
        dtn_work_bytes = full_vector_bytes
        carrier_bounded_work_bytes = int(audit["bounded_work_bytes"])
        adjoint_packed_work_bytes = int(
            adjoint_physical_action.audit["per_apply_bounded_temporary_bytes"]
        )
        phase_pack_incremental = int(
            2 * full_vector_bytes + adjoint_packed_work_bytes
        )
        phase_copy_incremental = int(3 * full_vector_bytes)
        phase_post_incremental = carrier_bounded_work_bytes
        worst_phase_incremental = max(
            phase_pack_incremental,
            phase_copy_incremental,
            phase_post_incremental,
        )
        predicted_incremental_work_bytes = int(
            carrier_bounded_work_bytes + adjoint_packed_work_bytes
        )
        incremental_work_excess_over_worst_phase_bytes = int(
            predicted_incremental_work_bytes - worst_phase_incremental
        )
        reserve_remaining_after_dtn_bytes = int(
            M6B_FIXED_RUNTIME_RESERVE_BYTES - dtn_work_bytes
        )
        lifecycle_basis = {
            "basis": "derived_not_measured",
            "full_owned_vector_bytes": full_vector_bytes,
            "callback_petsc_source_target_bytes": int(2 * full_vector_bytes),
            "callback_return_ndarray_copy_bytes": full_vector_bytes,
            "callback_peak_transient_bytes": int(3 * full_vector_bytes),
            "post_callback_adjoint_ndarray_and_correction_bytes": int(
                2 * full_vector_bytes
            ),
            "dtn_fe_target_work_bytes": dtn_work_bytes,
            "dtn_fe_target_work_coverage": "fixed_runtime_reserve_bytes",
            "dtn_fe_target_work_covered": (
                dtn_work_bytes <= M6B_FIXED_RUNTIME_RESERVE_BYTES
            ),
            "reserve_remaining_after_dtn_bytes": reserve_remaining_after_dtn_bytes,
            "carrier_bounded_work_bytes": carrier_bounded_work_bytes,
            "adjoint_packed_work_bytes": adjoint_packed_work_bytes,
            "phase_pack_incremental": phase_pack_incremental,
            "phase_copy_incremental": phase_copy_incremental,
            "phase_post_incremental": phase_post_incremental,
            "worst_phase_incremental": worst_phase_incremental,
            "predicted_incremental_work_bytes": predicted_incremental_work_bytes,
            "incremental_work_excess_over_worst_phase_bytes": (
                incremental_work_excess_over_worst_phase_bytes
            ),
            "incremental_formula_is_conservative": True,
            "dtn_not_in_incremental_formula": True,
            "worst_overlap_formula": (
                "worst_phase_incremental=max(phase_pack_incremental,"
                "phase_copy_incremental,phase_post_incremental); "
                "predicted_incremental_work_bytes=phase_post_incremental+"
                "adjoint_packed_work_bytes; dtn_fe_target_work_bytes is "
                "covered by base fixed_runtime_reserve_bytes and is not added "
                "to the incremental formula"
            ),
            "post_callback_vectors_not_simultaneous_with_callback_vectors": True,
        }
        summary = {
            "schema": M6B_W1_SCHEMA,
            "status": "measurement_complete",
            "formal_pass": False,
            "pde_pass": False,
            "qualification": "not_run",
            "source": h2b._light_source(),
            "scope": {
                "global_rows": M6B_GLOBAL_ROWS,
                "columns": 75,
                "operator_identity": identity["operator_identity"],
                "fine_space": identity["fine_space"],
                "global_matrix": False,
                "static_condensation": False,
                "trace_slab_pc": False,
                "ordinary_default": False,
            },
            "basis_manifest_sha256": basis_manifest_sha256,
            "store_manifest": str(manifest_path),
            "carrier_audit": audit,
            "jit_cache": {
                "source": str(jit_cache_source),
                "target": str(cache_dir),
                "source_before": source_cache_before,
                "target_before": target_cache_before,
                "target_after_forward": target_cache_after_forward,
                "target_after_adjoint": target_cache_after_adjoint,
                "target_after_surface": target_cache_after_surface,
                "target_final": final_cache,
                "source_after_forward": source_cache_after_forward,
                "source_after_adjoint": source_cache_after_adjoint,
                "source_after_surface": source_cache_after_surface,
                "source_final": source_cache_after,
                "forward_cache_reused": (
                    target_cache_after_forward == target_cache_before
                ),
                "adjoint_staging_changed_cache": (
                    target_cache_after_adjoint != target_cache_after_forward
                ),
                "surface_cache_reused_after_adjoint": (
                    target_cache_after_surface == target_cache_after_adjoint
                ),
                "target_frozen_unchanged": (
                    final_cache == target_cache_after_surface
                ),
                "source_unchanged": all(
                    record == source_cache_before
                    for record in (
                        source_cache_after_forward,
                        source_cache_after_adjoint,
                        source_cache_after_surface,
                        source_cache_after,
                    )
                ),
                "forward_delta": cache_deltas["forward_delta"],
                "adjoint_staging_delta": cache_deltas["adjoint_staging_delta"],
                "surface_delta": cache_deltas["surface_delta"],
                "final_delta": cache_deltas["final_delta"],
                "inventory_sha256": final_cache["inventory_sha256"],
            },
            "adjoint_identity": adjoint_identity,
            "memory_lifecycle": lifecycle_basis,
            "predicted_live_set": {
                "base_bytes": M6B_W1_BASE_PREDICTED_LIVE_SET_BYTES,
                "coarse_retained_bytes": audit["retained_total_bytes"],
                "coarse_bounded_work_bytes": audit["bounded_work_bytes"],
                "adjoint_volume_action_payload_bytes": int(
                    adjoint_physical_action.audit["retained_numeric_payload_global_max_bytes"]
                ),
                "adjoint_volume_action_work_bytes": int(
                    adjoint_physical_action.audit["per_apply_bounded_temporary_bytes"]
                ),
                "adjoint_identity_forward_count": 1,
                "adjoint_identity_adjoint_count": 2,
                "predicted_bytes": predicted,
                "limit_bytes": M6B_W1_PREDICTED_LIVE_SET_LIMIT_BYTES,
                "gate": True,
                "is_measurement": False,
            },
            "builder_peak_limit_bytes": M6B_W1_BUILDER_RSS_LIMIT_BYTES,
            "swap_limit_bytes": 0,
            "elapsed_wall_seconds": float(time.perf_counter() - started),
        }
        emit("summary_ready", qualification="not_run")
        _write_json(run_dir / "w1_builder_summary.json", _attach_evidence(summary))
        return 0
    finally:
        if template is not None:
            template.destroy()
        if outer_mat is not None:
            outer_mat.destroy()
        if outer_context is not None:
            outer_context.destroy()
        if dtn_action is not None:
            dtn_action.destroy()
        if physical_action is not None:
            physical_action.destroy()
        if adjoint_physical_action is not None:
            adjoint_physical_action.destroy()
        if surface_assemblers is not None:
            for assembler in surface_assemblers.values():
                destroy = getattr(assembler, "destroy", None)
                if destroy is not None:
                    destroy()
        del volume_ufl, adjoint_ufl, epsilon, abs_epsilon, beta
        gc.collect()


def _m6b_form_record(
    h2b: Any,
    action: Any,
    cache_dir: Path,
    cfg: Any,
    function_space: Any,
    role: str,
    beta: float,
) -> dict[str, Any]:
    record = h2b._form_record(
        action._action_form,
        action._action_ufl,
        cache_dir,
        cfg,
        function_space,
        role,
    )
    record.pop("proxy_identity", None)
    record["role"] = role
    record["beta"] = float(beta)
    record["beta_runtime_parameter"] = "fem.Constant"
    record["operator_identity"] = M6B_SHARED_VOLUME_OPERATOR
    record["representation"] = M6B_SHARED_VOLUME_REPRESENTATION
    return record


def _m6b_fixed_physics_identity(cfg: Any) -> dict[str, Any]:
    identity = {
        "use_pml": bool(cfg.use_pml),
        "pml_top_thickness": float(cfg.pml_top_thickness),
        "pml_bottom_thickness": float(cfg.pml_bottom_thickness),
        "divergence_penalty": float(cfg.divergence_penalty),
        "material_representation": "DG0_epsilon_and_abs_epsilon",
    }
    if (
        identity["use_pml"]
        or identity["pml_top_thickness"] != 0.0
        or identity["pml_bottom_thickness"] != 0.0
        or identity["divergence_penalty"] != 0.0
    ):
        raise ValueError("M6B shared volume physics is not the fixed no-PML contract")
    return identity


def _m6b_shared_kernel_identity(
    outer: Mapping[str, Any],
    shifted: Mapping[str, Any],
    cfg: Any,
    *,
    phase: str,
    shifted_beta: float = M6B_BETA,
) -> dict[str, Any]:
    if shifted_beta not in (M6B_BETA, M6B_W3_BETA):
        raise ValueError("M6B shifted shared-kernel beta is not fixed")
    fixed_physics = _m6b_fixed_physics_identity(cfg)
    required = (
        "beta",
        "beta_runtime_parameter",
        "operator_identity",
        "representation",
        "module_name",
        "ufl_signature",
        "ufcx_signature",
        "code_state",
    )
    if not isinstance(outer, Mapping) or not isinstance(shifted, Mapping):
        raise ValueError("M6B shared volume form records are incomplete")
    if any(key not in outer or key not in shifted for key in required):
        raise ValueError("M6B shared volume form identity is incomplete")
    if (
        outer["beta"] != 0.0
        or shifted["beta"] != shifted_beta
        or outer["beta_runtime_parameter"] != "fem.Constant"
        or shifted["beta_runtime_parameter"] != "fem.Constant"
        or outer["operator_identity"] != M6B_SHARED_VOLUME_OPERATOR
        or shifted["operator_identity"] != M6B_SHARED_VOLUME_OPERATOR
        or outer["representation"] != M6B_SHARED_VOLUME_REPRESENTATION
        or shifted["representation"] != M6B_SHARED_VOLUME_REPRESENTATION
        or outer["module_name"] != shifted["module_name"]
        or outer["ufl_signature"] != shifted["ufl_signature"]
        or outer["ufcx_signature"] != shifted["ufcx_signature"]
    ):
        raise ValueError("M6B physical/shifted shared kernel identity changed")
    return {
        "schema": M6B_SHARED_VOLUME_SCHEMA,
        "phase": str(phase),
        "operator_identity": M6B_SHARED_VOLUME_OPERATOR,
        "representation": M6B_SHARED_VOLUME_REPRESENTATION,
        "fixed_physics": fixed_physics,
        "beta_runtime_parameter": "fem.Constant",
        "outer_beta": 0.0,
        "shifted_beta": shifted_beta,
        "module_name": outer["module_name"],
        "ufl_signature": outer["ufl_signature"],
        "ufcx_signature": outer["ufcx_signature"],
        "outer_code_state": outer["code_state"],
        "shifted_code_state": shifted["code_state"],
        "same_module": True,
        "same_ufl_signature": True,
        "same_ufcx_signature": True,
    }


def _m6b_shared_kernel_valid(
    value: Any, *, phase: str, shifted_beta: float = M6B_BETA
) -> bool:
    if shifted_beta not in (M6B_BETA, M6B_W3_BETA):
        return False
    required = {
        "schema",
        "phase",
        "operator_identity",
        "representation",
        "fixed_physics",
        "beta_runtime_parameter",
        "outer_beta",
        "shifted_beta",
        "module_name",
        "ufl_signature",
        "ufcx_signature",
        "outer_code_state",
        "shifted_code_state",
        "same_module",
        "same_ufl_signature",
        "same_ufcx_signature",
    }
    if phase not in {"stage", "builder", "mpi1"}:
        return False
    if not isinstance(value, Mapping) or set(value) != required:
        return False
    physics = value["fixed_physics"]
    expected_outer_state = "cold_decl_impl_generated"
    expected_shifted_state = "hit_no_new_decl_impl"
    if phase == "mpi1":
        expected_outer_state = expected_shifted_state
    return bool(
        value["schema"] == M6B_SHARED_VOLUME_SCHEMA
        and value["phase"] == ("stage" if phase == "builder" else phase)
        and value["operator_identity"] == M6B_SHARED_VOLUME_OPERATOR
        and value["representation"] == M6B_SHARED_VOLUME_REPRESENTATION
        and isinstance(physics, Mapping)
        and set(physics)
        == {
            "use_pml",
            "pml_top_thickness",
            "pml_bottom_thickness",
            "divergence_penalty",
            "material_representation",
        }
        and physics["use_pml"] is False
        and physics["pml_top_thickness"] == 0.0
        and physics["pml_bottom_thickness"] == 0.0
        and physics["divergence_penalty"] == 0.0
        and physics["material_representation"] == "DG0_epsilon_and_abs_epsilon"
        and value["beta_runtime_parameter"] == "fem.Constant"
        and value["outer_beta"] == 0.0
        and value["shifted_beta"] == shifted_beta
        and isinstance(value["module_name"], str)
        and value["module_name"].startswith("libffcx_forms_")
        and isinstance(value["ufl_signature"], str)
        and bool(value["ufl_signature"])
        and isinstance(value["ufcx_signature"], str)
        and bool(value["ufcx_signature"])
        and value["outer_code_state"] == expected_outer_state
        and value["shifted_code_state"] == expected_shifted_state
        and value["same_module"] is True
        and value["same_ufl_signature"] is True
        and value["same_ufcx_signature"] is True
    )


def _m6b_form_record_bound(
    record: Any,
    shared: Any,
    *,
    role: str,
    beta: float,
    code_state: str,
    shared_phase: str = "stage",
    shared_shifted_beta: float = M6B_BETA,
) -> bool:
    if not _m6b_shared_kernel_valid(
        shared, phase=shared_phase, shifted_beta=shared_shifted_beta
    ):
        return False
    if not isinstance(record, Mapping):
        return False
    required = {
        "role",
        "beta",
        "beta_runtime_parameter",
        "operator_identity",
        "representation",
        "module_name",
        "ufl_signature",
        "ufcx_signature",
        "code_state",
    }
    if not required.issubset(record):
        return False
    return bool(
        record["role"] == role
        and record["beta"] == beta
        and record["beta_runtime_parameter"] == "fem.Constant"
        and record["operator_identity"] == shared["operator_identity"]
        and record["representation"] == shared["representation"]
        and record["module_name"] == shared["module_name"]
        and record["ufl_signature"] == shared["ufl_signature"]
        and record["ufcx_signature"] == shared["ufcx_signature"]
        and record["code_state"] == code_state
    )


def _m6b_form_records_bound(
    outer: Any,
    shifted: Any,
    shared: Any,
    *,
    phase: str,
    shifted_beta: float = M6B_BETA,
) -> bool:
    if phase not in {"stage", "mpi1"}:
        return False
    outer_state = "cold_decl_impl_generated" if phase == "stage" else "hit_no_new_decl_impl"
    return bool(
        _m6b_form_record_bound(
            outer,
            shared,
            role="outer_volume",
            beta=0.0,
            code_state=outer_state,
            shared_phase=phase,
            shared_shifted_beta=shifted_beta,
        )
        and _m6b_form_record_bound(
            shifted,
            shared,
            role="shifted_volume",
            beta=shifted_beta,
            code_state="hit_no_new_decl_impl",
            shared_phase=phase,
            shared_shifted_beta=shifted_beta,
        )
    )


def _m6b_material_tag_coverage_valid(value: Any, *, owned_cells: int) -> bool:
    return bool(
        isinstance(value, Mapping)
        and set(value) == {
            "owned_cell_count",
            "allowed_tag_values",
            "tag_counts",
            "complete",
        }
        and value["owned_cell_count"] == owned_cells
        and value["allowed_tag_values"] == {"air": 1, "substrate": 2, "grating": 3}
        and isinstance(value["tag_counts"], Mapping)
        and set(value["tag_counts"]) == {"air", "substrate", "grating"}
        and all(
            type(value["tag_counts"][key]) is int
            and value["tag_counts"][key] >= 0
            for key in value["tag_counts"]
        )
        and sum(value["tag_counts"].values()) == owned_cells
        and value["complete"] is True
    )


def _m6b_runtime_identity(
    h2b: Any, h2a: Any, comm: Any, *, compiler_probe: bool, compiler: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    import dolfinx
    import mpi4py
    import petsc4py
    import slepc4py

    identity = dict(
        h2b._runtime_identity(
            h2a,
            compiler_probe=compiler_probe,
            compiler=compiler,
        )
    )
    identity.update(
        {
            "mpi_size": int(comm.size),
            "linux_abi": os.name == "posix",
            "package_paths": {
                "petsc4py": str(petsc4py.__file__),
                "slepc4py": str(slepc4py.__file__),
                "dolfinx": str(dolfinx.__file__),
                "mpi4py": str(mpi4py.__file__),
            },
        }
    )
    return identity


def _m6b_w6a_runtime_valid(
    value: Any, *, frozen_compiler: Mapping[str, Any]
) -> bool:
    if not isinstance(value, Mapping) or not isinstance(frozen_compiler, Mapping):
        return False
    executable = value.get("sys_executable")
    threads = value.get("threads")
    paths = value.get("package_paths")
    required_threads = (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    )
    return bool(
        value.get("qualified_activation") == "1"
        and value.get("petsc_scalar_type") == "complex128"
        and value.get("petsc_int_type") == "int32"
        and value.get("mpi_size") == 1
        and value.get("linux_abi") is True
        and isinstance(executable, str)
        and Path(executable).is_absolute()
        and Path(executable).parent.name == "bin"
        and Path(executable).parent.parent.name == ".venv"
        and isinstance(threads, Mapping)
        and all(threads.get(name) == "1" for name in required_threads)
        and isinstance(paths, Mapping)
        and set(paths) == {"petsc4py", "slepc4py", "dolfinx", "mpi4py"}
        and all(
            isinstance(path, str)
            and Path(path).is_absolute()
            and "/mnt/c" not in path
            and "\\" not in path
            for path in paths.values()
        )
        and value.get("compiler") == dict(frozen_compiler)
    )


def _m6b_p6_identity(mesh_data: Any, function_space: Any, floquet: Any) -> dict[str, int]:
    index_map = function_space.dofmap.index_map
    return {
        "global_cells": int(mesh_data.mesh.topology.index_map(3).size_global),
        "local_cells": int(mesh_data.mesh.topology.index_map(3).size_local),
        "local_nloc": int(function_space.element.space_dimension),
        "global_rows": int(index_map.size_global * function_space.dofmap.index_map_bs),
        "constraint_count": int(floquet.num_constraints),
    }


def _m6b_progress_valid(path: Path, phase: str, expected: Sequence[str]) -> bool:
    observed: list[str] = []
    elapsed = 0.0
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            item = json.loads(line)
            value = item.get("elapsed_wall_seconds") if isinstance(item, Mapping) else None
            if (
                not isinstance(item, Mapping)
                or item.get("schema") != f"{M6B_SCHEMA}.progress.v1"
                or item.get("phase") != phase
                or item.get("event") not in expected
                or item["event"] in observed
                or type(value) not in (int, float)
                or not math.isfinite(float(value))
                or float(value) < elapsed
            ):
                return False
            observed.append(str(item["event"]))
            elapsed = float(value)
        return tuple(observed) == tuple(expected)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return False


def _m6b_expected_p6(identity: Mapping[str, Any]) -> bool:
    return dict(identity) == {
        "global_cells": M6B_GLOBAL_CELLS,
        "local_cells": M6B_GLOBAL_CELLS,
        "local_nloc": M6B_LOCAL_NLOC,
        "global_rows": M6B_GLOBAL_ROWS,
        "constraint_count": M6B_CONSTRAINTS,
    }


def _run_m6b_stage_worker(run_dir: Path) -> int:
    """Compile the exact online forms into one isolated cache and exit."""

    import gc
    import time

    from mpi4py import MPI

    h2b = __import__("benchmarks.run_task037_extra_h2b", fromlist=["*"])
    h2a = h2b._lazy_h2a()
    m6a = __import__("benchmarks.run_task037_extra_m6", fromlist=["*"])
    from dolfinx import fem
    from src.solvers.dtn_port_3d import _incident_top_traction_form
    from src.solvers.hcurl_rank_one_mpc_action import build_task037_extra_h1r2_mpc_action
    from src.solvers.hcurl_h2b_m6b_shifted_patch_pc import build_m6b_volume_form

    comm = MPI.COMM_WORLD
    if comm.size != 1:
        raise RuntimeError("M6B stage is fixed to MPI1")
    run_dir = run_dir.resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    progress_path = run_dir / "m6b_stage_progress.jsonl"
    summary_path = run_dir / "m6b_stage_summary.json"
    source_start = h2b._light_source()
    status = "gate_failed"
    error: str | None = None
    runtime: dict[str, Any] | None = None
    p6: dict[str, Any] | None = None
    forms: dict[str, Any] | None = None
    cache_inventory: list[dict[str, Any]] | None = None
    try:
        with progress_path.open("w", encoding="utf-8") as markers:
            _m6b_emit(markers, "stage", "authority_validated", started)
            cfg, mesh_data, function_space, floquet, modes = m6a._production_objects(
                run_dir, mesh_name="m6b_stage_mesh"
            )
            _m6b_emit(markers, "stage", "mesh_ready", started)
            _m6b_emit(markers, "stage", "space_ready", started)
            _m6b_emit(markers, "stage", "floquet_mpc_ready", started)
            if len(modes) != 80:
                raise ValueError("M6B mode authority is not 80 modes")
            cache_dir = run_dir / "jit_cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            proxy_forms = h2a._proxy_forms(
                function_space, mesh_data, cfg, cache_dir=cache_dir
            )
            _m6b_emit(markers, "stage", "proxy_forms_ready", started)
            del proxy_forms
            gc.collect()
            physical_ufl, epsilon0, abs_epsilon0, beta0, tag_coverage = build_m6b_volume_form(
                function_space, mesh_data, cfg, beta=0.0
            )
            jit_options = h2b._expected_jit_options(cache_dir)
            physical_action = build_task037_extra_h1r2_mpc_action(
                physical_ufl,
                floquet.mpc,
                task037_extra_h1r2=True,
                jit_options=jit_options,
            )
            physical_record = _m6b_form_record(
                h2b,
                physical_action,
                cache_dir,
                cfg,
                function_space,
                "outer_volume",
                0.0,
            )
            physical_action.destroy()
            del physical_action, physical_ufl, epsilon0, abs_epsilon0, beta0
            gc.collect()
            _m6b_emit(markers, "stage", "outer_form_ready", started)
            shifted_ufl, epsilon1, abs_epsilon1, beta1, shifted_tag_coverage = build_m6b_volume_form(
                function_space, mesh_data, cfg, beta=M6B_BETA
            )
            if shifted_tag_coverage != tag_coverage:
                raise ValueError("M6B shared volume material tag coverage changed")
            shifted_action = build_task037_extra_h1r2_mpc_action(
                shifted_ufl,
                floquet.mpc,
                task037_extra_h1r2=True,
                jit_options=jit_options,
            )
            shifted_record = _m6b_form_record(
                h2b,
                shifted_action,
                cache_dir,
                cfg,
                function_space,
                "shifted_volume",
                M6B_BETA,
            )
            shifted_action.destroy()
            del shifted_action, shifted_ufl, epsilon1, abs_epsilon1, beta1
            gc.collect()
            _m6b_emit(markers, "stage", "shifted_form_ready", started)
            shared_volume_kernel = _m6b_shared_kernel_identity(
                physical_record,
                shifted_record,
                cfg,
                phase="stage",
            )
            assemblers = m6a._surface_assemblers(
                function_space, mesh_data, cfg, modes, cache_dir
            )
            incident_form = fem.form(
                _incident_top_traction_form(function_space, mesh_data, cfg),
                jit_options=jit_options,
            )
            surface_identity = m6a._surface_identity(cache_dir, modes)
            cache_inventory = h2b._cache_snapshot(cache_dir)
            forms = {
                "outer_volume": physical_record,
                "shifted_volume": shifted_record,
                "shared_volume_kernel": shared_volume_kernel,
                "material_tag_coverage": tag_coverage,
                "surface": surface_identity,
                "incident_form_count": 1,
                "cache_inventory": cache_inventory,
            }
            p6 = _m6b_p6_identity(mesh_data, function_space, floquet)
            if not _m6b_expected_p6(p6):
                raise ValueError(f"M6B p6 identity mismatch: {p6}")
            runtime = _m6b_runtime_identity(h2b, h2a, comm, compiler_probe=True)
            _m6b_emit(markers, "stage", "surface_forms_ready", started)
            _m6b_emit(markers, "stage", "summary_ready", started)
            del assemblers, incident_form
            del mesh_data, function_space, floquet, modes, cfg
            gc.collect()
            status = "measurement_complete"
    except h2b._worker_error_types() as exc:
        error = f"{type(exc).__name__}: {exc}"
    source_end = h2b._light_source()
    payload = _attach_evidence(
        {
            "schema": M6B_STAGE_SCHEMA,
            "status": status,
            "scope": _m6b_scope(phase="stage"),
            "events": list(M6B_STAGE_EVENTS),
            "p6": p6,
            "forms": forms,
            "cache_inventory": cache_inventory,
            "runtime_identity": runtime,
            "source_at_start": source_start,
            "source_at_end": source_end,
            "error": error,
            "elapsed_wall_seconds": float(time.perf_counter() - started),
        }
    )
    _write_json(summary_path, payload)
    return 0 if status == "measurement_complete" else 1


def _m6b_patch_closure(
    matrix: Any,
    patch_rows: Any,
    action: Any,
    source: Any,
) -> float:
    import numpy as np
    from petsc4py import PETSc

    rows = np.asarray(patch_rows, dtype=np.int64)
    owned_start, owned_end = map(int, source.getOwnershipRange())
    local_rows = rows - owned_start
    if np.any(local_rows < 0) or np.any(rows >= owned_end):
        raise ValueError("M6B patch closure rows are not owned by the builder")
    with source.localForm() as local_source:
        local_source.array_w[:] = 0.0
        local_source.array_w[local_rows] = np.asarray(
            [
                np.sin(0.0021 * row) + 1j * np.cos(0.0011 * row)
                for row in rows.tolist()
            ],
            dtype=np.complex128,
        )
    source.ghostUpdate(
        addv=PETSc.InsertMode.INSERT_VALUES,
        mode=PETSc.ScatterMode.FORWARD,
    )
    values = np.asarray(source.getArray(readonly=True), dtype=np.complex128)
    result = action.mult(source)
    observed = np.array(
        result.getArray(readonly=True), dtype=np.complex128, copy=True
    )
    expected = np.asarray(matrix, dtype=np.complex128) @ values[local_rows]
    actual = observed[local_rows]
    del result
    return float(
        np.linalg.norm(actual - expected)
        / max(float(np.linalg.norm(expected)), 1.0e-300)
    )


def _run_m6b_builder(run_dir: Path) -> int:
    """Build fresh shifted class blocks and stream 84 row-complete LU factors."""

    import gc
    import time
    from types import SimpleNamespace

    import numpy as np
    from mpi4py import MPI

    h2b = __import__("benchmarks.run_task037_extra_h2b", fromlist=["*"])
    h2a = h2b._lazy_h2a()
    m6a = __import__("benchmarks.run_task037_extra_m6", fromlist=["*"])
    from petsc4py import PETSc
    from src.common.config_3d import target_stage4_config
    from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
    from src.solvers.common_3d_solve import _create_nedelec_space
    from src.solvers.hcurl_h2b_m6b_shifted_lu_store import (
        build_h2b_m6b_shifted_lu_factor,
        stream_write_h2b_m6b_shifted_lu_patch_store,
    )
    from src.solvers.hcurl_h2b_m6b_shifted_patch_pc import (
        build_m6b_volume_form,
        m6b_shifted_local_matrix,
    )
    from src.solvers.hcurl_h2b_p1_factor_store import (
        H2BP1ClassBlockAuthority,
        discover_h2b_p1_neighborhoods,
        stream_h2b_p1_neighborhood,
    )
    from src.solvers.hcurl_r2_constrained_local_block import (
        build_h2a_r2_cell_expansion,
        build_h2a_r2_transformed_block,
    )
    from src.solvers.hcurl_r2_factor_store import (
        H2AR2CellReference,
        load_h2a_r2_factor_store,
    )

    comm = MPI.COMM_WORLD
    if comm.size != 1:
        raise RuntimeError("M6B builder is fixed to MPI1")
    run_dir = run_dir.resolve()
    started = time.perf_counter()
    progress_path = run_dir / "m6b_builder_progress.jsonl"
    summary_path = run_dir / "m6b_builder_summary.json"
    source_start = h2b._light_source()
    status = "gate_failed"
    error: str | None = None
    runtime: dict[str, Any] | None = None
    p6: dict[str, Any] | None = None
    form_record: dict[str, Any] | None = None
    store_manifest: Path | None = None
    store_audit: dict[str, Any] | None = None
    sample_closure: dict[str, float] = {}
    class_block_audit: dict[str, Any] | None = None
    shared_volume_kernel: dict[str, Any] | None = None
    tag_coverage: dict[str, Any] | None = None
    cache_before: Any = None
    cache_after: Any = None
    shifted_action = None
    shifted_ufl = None
    epsilon = None
    abs_epsilon = None
    beta_constant = None
    source_vec = None
    try:
        with progress_path.open("w", encoding="utf-8") as markers:
            stage = h2b._read_json(run_dir / "m6b_stage_summary.json")
            if (
                stage.get("status") != "measurement_complete"
                or not h2b._evidence_valid(stage)
                or stage.get("forms", {}).get("cache_inventory") is None
            ):
                raise ValueError("M6B stage authority is incomplete")
            _m6b_emit(markers, "builder", "authority_validated", started)
            cfg = target_stage4_config(degree=6, h_nm=10.0)
            mesh_data = build_airbox_mesh_3d(cfg, run_dir / "m6b_builder_mesh")
            _m6b_emit(markers, "builder", "mesh_ready", started)
            function_space = _create_nedelec_space(mesh_data.mesh, cfg)
            _m6b_emit(markers, "builder", "space_ready", started)
            floquet = h2a.build_double_floquet_mpc(function_space, mesh_data, cfg)
            p6 = _m6b_p6_identity(mesh_data, function_space, floquet)
            if not _m6b_expected_p6(p6):
                raise ValueError(f"M6B builder p6 identity mismatch: {p6}")
            _m6b_emit(markers, "builder", "floquet_mpc_ready", started)
            cache_dir = run_dir / "jit_cache"
            cache_before = h2b._cache_snapshot(cache_dir)
            shifted_ufl, epsilon, abs_epsilon, beta_constant, tag_coverage = build_m6b_volume_form(
                function_space, mesh_data, cfg, beta=M6B_BETA
            )
            shifted_action = __import__(
                "src.solvers.hcurl_rank_one_mpc_action",
                fromlist=["build_task037_extra_h1r2_mpc_action"],
            ).build_task037_extra_h1r2_mpc_action(
                shifted_ufl,
                floquet.mpc,
                task037_extra_h1r2=True,
                jit_options=h2b._expected_jit_options(cache_dir),
            )
            form_record = _m6b_form_record(
                h2b,
                shifted_action,
                cache_dir,
                cfg,
                function_space,
                "shifted_volume",
                M6B_BETA,
            )
            shared_volume_kernel = _m6b_shared_kernel_identity(
                stage["forms"]["outer_volume"],
                form_record,
                cfg,
                phase="stage",
            )
            if shared_volume_kernel != stage["forms"].get("shared_volume_kernel"):
                raise ValueError("M6B builder shared volume identity differs from stage")
            authority = h2b._authority()
            r2_store = load_h2a_r2_factor_store(
                h2b.H2B_R2_MANIFEST, task037_extra_h2a_r2=True
            )
            discovery = h2a._discover_cell_references(
                function_space,
                mesh_data,
                cfg,
                floquet,
                geometry_tolerance=h2a.floquet_geometry_tolerance(cfg),
            )
            class_inventory = authority["r0"]["class_inventory"]
            key_to_id = {
                str(item["class_key_sha256"]): int(item["class_id"])
                for item in class_inventory
            }
            blocks = tuple(floquet.phase_independent_topology.blocks)
            cell_refs: list[H2AR2CellReference] = []
            expansions: dict[int, Any] = {}
            for reference in discovery["references"]:
                cell_dofs = np.asarray(reference.local_dofs, dtype=np.int64)
                class_id = key_to_id.get(h2a._r0_digest(reference.class_key))
                if class_id is None:
                    raise ValueError("M6B discovery class is not in R0 authority")
                expansion = build_h2a_r2_cell_expansion(
                    h2a._blocks_for_cell(blocks, cell_dofs),
                    cell_dofs,
                    function_space.dofmap.index_map,
                    index_map_bs=int(function_space.dofmap.index_map_bs),
                    phase_x=floquet.phase_x,
                    phase_y=floquet.phase_y,
                    phase_corner=floquet.phase_corner,
                )
                old = expansions.get(class_id)
                if old is not None and old.pattern_sha256 != expansion.pattern_sha256:
                    raise ValueError("M6B expansion pattern differs within class")
                expansions.setdefault(class_id, expansion)
                cell_refs.append(H2AR2CellReference(class_id, expansion.independent_global_rows))
            if len(cell_refs) != M6B_GLOBAL_CELLS or len(r2_store.cells) != len(cell_refs):
                raise ValueError("M6B cell reference count mismatch")
            if any(
                len(cell.independent_global_rows) != M6B_LOCAL_NLOC
                for cell in cell_refs
            ):
                raise ValueError("M6B cell row-complete references are not 882")
            if any(
                a.class_id != b.class_id
                or not np.array_equal(a.independent_global_rows, b.independent_global_rows)
                for a, b in zip(r2_store.cells, cell_refs, strict=True)
            ):
                raise ValueError("M6B fresh cell rows differ from frozen topology")
            del r2_store
            gc.collect()
            proxy_forms = h2a._proxy_forms(function_space, mesh_data, cfg, cache_dir=cache_dir)
            cache_after = h2b._cache_snapshot(cache_dir)
            if (
                cache_before != stage["forms"]["cache_inventory"]
                or cache_before != cache_after
                or form_record.get("code_state") != "hit_no_new_decl_impl"
            ):
                raise ValueError("M6B builder form/cache identity changed after proxy construction")
            _m6b_emit(markers, "builder", "class_expansion_ready", started)
            representative_by_class = {
                int(key_to_id[h2a._r0_digest(key)]): item
                for key, item in discovery["representatives"].items()
            }
            if len(class_inventory) != 24:
                raise ValueError("M6B class inventory is not the fixed 24-class authority")
            class_matrices: list[np.ndarray] = []
            class_shas: list[str] = []
            for class_id in range(len(class_inventory)):
                representative = representative_by_class[class_id]
                cell = int(representative["cell"])
                tag = int(representative["tag"])
                curl, widths, cell_info = h2a.tabulate_task037_extra_h2a_cell_tensor(
                    proxy_forms[0], function_space, mesh_data.cell_tags, cell,
                    geometry_tolerance=h2a.floquet_geometry_tolerance(cfg),
                )
                mass, mass_widths, mass_info = h2a.tabulate_task037_extra_h2a_cell_tensor(
                    proxy_forms[1], function_space, mesh_data.cell_tags, cell,
                    geometry_tolerance=h2a.floquet_geometry_tolerance(cfg),
                )
                if widths != mass_widths or cell_info != mass_info:
                    raise ValueError("M6B curl/mass tensor identity mismatch")
                epsilon_value = h2a._material_epsilon(cfg, tag)
                local = m6b_shifted_local_matrix(
                    curl,
                    mass,
                    epsilon_value,
                    cfg.k0,
                    M6B_BETA,
                )
                transformed = build_h2a_r2_transformed_block(
                    local, expansions[class_id]
                )
                class_matrices.append(transformed)
                class_shas.append(
                    hashlib.sha256(
                        memoryview(np.ascontiguousarray(transformed)).cast("B")
                    ).hexdigest()
                )
                del curl, mass, local, transformed
            class_authority = H2BP1ClassBlockAuthority(
                np.arange(len(class_matrices), dtype=np.int32),
                tuple(class_shas),
                tuple(class_matrices),
            )
            class_block_audit = {
                key: value
                for key, value in class_authority.audit.items()
                if key != "retained_payload_components"
            }
            class_block_audit["retained_payload_components"] = dict(
                class_authority.audit["retained_payload_components"]
            )
            class_block_audit.update(
                {
                    "operator_identity": M6B_SHIFTED_OPERATOR,
                    "numeric_matrix_source": "fresh_transformed_B_beta_class_block",
                    "retained_class_block_bytes": int(
                        class_authority.audit["retained_payload_bytes"]
                    ),
                    "fresh_B_beta_class_count": len(class_inventory),
                    "fresh_B_beta_matrix_count": len(class_shas),
                    "r2_numeric_store_used_for_blocks": False,
                }
            )
            class_count = len(class_matrices)
            del class_matrices
            gc.collect()
            _m6b_emit(
                markers,
                "builder",
                "class_blocks_ready",
                started,
                class_count=class_count,
            )
            inventory_by_id = {
                int(item["class_id"]): item for item in class_inventory
            }
            fresh_class_records = tuple(
                SimpleNamespace(
                    class_id=class_id,
                    class_key_sha256=inventory_by_id[class_id]["class_key_sha256"],
                    constraint_pattern_sha256=inventory_by_id[class_id][
                        "constraint_pattern_sha256"
                    ],
                    expansion_pattern_sha256=expansions[class_id].pattern_sha256,
                    numeric_matrix_sha256=class_shas[class_id],
                    numeric_matrix_shape=tuple(
                        int(value) for value in class_authority.matrix_for_factor(class_id).shape
                    ),
                    numeric_matrix_dtype=str(
                        class_authority.matrix_for_factor(class_id).dtype
                    ),
                    expansion=expansions[class_id],
                )
                for class_id in range(len(class_inventory))
            )
            p1_discovery = discover_h2b_p1_neighborhoods(
                cell_refs,
                fresh_class_records,
                class_inventory,
                {
                    "operator": M6B_SHIFTED_OPERATOR,
                    "numeric_matrix_source": "fresh_transformed_B_beta_class_block",
                },
                task037_extra_h2b=True,
            )
            if p1_discovery["unique_neighborhood_count"] != M6B_FACTOR_COUNT:
                raise ValueError("M6B neighborhood count mismatch")
            neighborhoods = p1_discovery["neighborhoods"]
            _m6b_emit(
                markers,
                "builder",
                "neighborhood_ready",
                started,
                neighborhood_count=len(neighborhoods),
            )
            source_vec = shifted_action.output_vector.duplicate()
            # The generator keeps only the matrix currently handed to the
            # streaming writer; sampled repeats replace the first matrix.
            def matrix_records():
                for neighborhood in neighborhoods:
                    first = stream_h2b_p1_neighborhood(
                        neighborhood, cell_refs, class_authority, task037_extra_h2b=True
                    )
                    first_matrix = first.pop("matrix")
                    matrix_sha = first["matrix_sha256"]
                    record = {
                        "neighborhood_id": int(neighborhood.neighborhood_id),
                        "key_sha256": neighborhood.key_sha256,
                        "cell_ordinals": list(neighborhood.cell_ordinals),
                        "multiplicity": len(neighborhood.cell_ordinals),
                        "central_class_id": int(neighborhood.central_class_id),
                        "touching_cell_ordinals": list(neighborhood.touching_cell_ordinals),
                        "touching_class_ids": list(neighborhood.touching_class_ids),
                        "touching_count": int(neighborhood.touching_cell_count),
                        "repeat_performed": neighborhood.neighborhood_id in {0, 42, 83},
                    }
                    matrix_to_write = first_matrix
                    if neighborhood.neighborhood_id in {0, 42, 83}:
                        first_factor = build_h2b_m6b_shifted_lu_factor(
                            first_matrix,
                            beta=M6B_BETA,
                            matrix_sha256=matrix_sha,
                            task037_extra_m6b=True,
                        )
                        first_factor_sha = first_factor.factor_sha256
                        del first_factor, first_matrix
                        first_matrix = None
                        repeat = stream_h2b_p1_neighborhood(
                            neighborhood, cell_refs, class_authority, task037_extra_h2b=True
                        )
                        repeat_matrix = repeat.pop("matrix")
                        repeat_matrix_sha = repeat["matrix_sha256"]
                        repeat_factor = build_h2b_m6b_shifted_lu_factor(
                            repeat_matrix,
                            beta=M6B_BETA,
                            matrix_sha256=repeat_matrix_sha,
                            task037_extra_m6b=True,
                        )
                        repeat_factor_sha = repeat_factor.factor_sha256
                        if repeat_matrix_sha != matrix_sha:
                            raise ValueError("M6B sampled shifted patch is nondeterministic")
                        if repeat_factor_sha != first_factor_sha:
                            raise ValueError("M6B sampled shifted factor is nondeterministic")
                        sample_closure[str(neighborhood.neighborhood_id)] = _m6b_patch_closure(
                            repeat_matrix,
                            neighborhood.patch_rows,
                            shifted_action,
                            source_vec,
                        )
                        if sample_closure[str(neighborhood.neighborhood_id)] > 1.0e-11:
                            raise ValueError("M6B shifted patch action closure failed")
                        sample_matrix_sha = repeat_matrix_sha
                        sample_factor_sha = repeat_factor_sha
                        matrix_to_write = repeat_matrix
                        del repeat_factor, repeat_matrix, repeat
                        record.update(
                            {
                                "first_matrix_sha256": matrix_sha,
                                "repeat_matrix_sha256": sample_matrix_sha,
                                "expected_matrix_sha256": sample_matrix_sha,
                                "repeat_factor_sha256": sample_factor_sha,
                                "expected_factor_sha256": sample_factor_sha,
                            }
                        )
                    else:
                        del first
                    yield record, matrix_to_write
                    del matrix_to_write, first_matrix
            cell_counts = np.asarray(
                [len(cell.independent_global_rows) for cell in cell_refs],
                dtype=np.int64,
            )
            row_offsets = np.empty(cell_counts.size + 1, dtype=np.int64)
            row_offsets[0] = 0
            row_offsets[1:] = np.cumsum(cell_counts, dtype=np.int64)
            cell_rows = np.concatenate(
                [cell.independent_global_rows for cell in cell_refs]
            ).astype(np.int64, copy=False)
            if row_offsets[-1] != cell_rows.size or cell_rows.size != M6B_GLOBAL_CELLS * M6B_LOCAL_NLOC:
                raise ValueError("M6B cell row offsets do not close at 252*882")
            store_manifest = stream_write_h2b_m6b_shifted_lu_patch_store(
                matrix_records(),
                run_dir / "shifted_lu_store",
                p1_discovery["cell_neighborhood_ids"],
                row_offsets,
                cell_rows,
                neighborhoods=[
                    {
                        "neighborhood_id": int(item.neighborhood_id),
                        "key_sha256": item.key_sha256,
                        "cell_ordinals": list(item.cell_ordinals),
                        "multiplicity": len(item.cell_ordinals),
                        "factor_id": 0,
                    }
                    for item in neighborhoods
                ],
                identity={
                    "source_identity": source_start,
                    "stage_manifest_sha256": h2b._sha256_file(run_dir / "m6b_stage_summary.json"),
                    "r2_metadata_manifest_sha256": h2b.H2B_R2_MANIFEST_SHA256,
                    "r2_role": "topology_and_class_identity_only",
                    "r2_numeric_store_used_for_blocks": False,
                    "beta": M6B_BETA,
                    "operator": M6B_SHIFTED_OPERATOR,
                },
                beta=M6B_BETA,
                expected_factor_count=M6B_FACTOR_COUNT,
                expected_neighborhood_count=M6B_FACTOR_COUNT,
                task037_extra_m6b=True,
            )
            manifest = h2b._read_json(store_manifest)
            store_audit = dict(manifest["audit"])
            if store_audit["factor_count"] != M6B_FACTOR_COUNT:
                raise ValueError("M6B shifted store factor count mismatch")
            _m6b_emit(markers, "builder", "patch_stream_ready", started)
            _m6b_emit(markers, "builder", "factor_store_ready", started)
            _m6b_emit(markers, "builder", "summary_ready", started)
            del class_authority, fresh_class_records, proxy_forms
            runtime = _m6b_runtime_identity(h2b, h2a, comm, compiler_probe=False, compiler=stage["runtime_identity"]["compiler"])
            status = "measurement_complete"
    except h2b._worker_error_types() as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        for item in (source_vec,):
            if item is not None:
                item.destroy()
        if shifted_action is not None:
            shifted_action.destroy()
        del shifted_ufl, epsilon, abs_epsilon, beta_constant
        gc.collect()
    source_end = h2b._light_source()
    payload = _attach_evidence(
        {
            "schema": M6B_BUILDER_SCHEMA,
            "status": status,
            "scope": _m6b_scope(phase="builder"),
            "events": list(M6B_BUILDER_EVENTS),
            "p6": p6,
            "form": form_record,
            "shared_volume_kernel": shared_volume_kernel if form_record else None,
            "material_tag_coverage": tag_coverage,
            "cache": {
                "stage": stage["forms"]["cache_inventory"],
                "before": cache_before,
                "after": cache_after,
                "unchanged": cache_before == cache_after,
            },
            "factor_store": _artifact(run_dir, "shifted_lu_store/manifest.json") if store_manifest else None,
            "factor_audit": store_audit,
            "class_block_audit": class_block_audit,
            "sample_patch_action_closure": sample_closure,
            "runtime_identity": runtime,
            "source_at_start": source_start,
            "source_at_end": source_end,
            "error": error,
            "elapsed_wall_seconds": float(time.perf_counter() - started),
        }
    )
    _write_json(summary_path, payload)
    return 0 if status == "measurement_complete" else 1


def _run_m6b_online_worker(run_dir: Path) -> int:
    """Load the shifted store and run the fixed right-FGMRES screen."""

    import gc
    import time

    import numpy as np
    from mpi4py import MPI
    from petsc4py import PETSc

    h2b = __import__("benchmarks.run_task037_extra_h2b", fromlist=["*"])
    h2a = h2b._lazy_h2a()
    m6a = __import__("benchmarks.run_task037_extra_m6", fromlist=["*"])
    from dolfinx import fem
    from src.solvers.dtn_port_3d import _assemble_mpc_form_vector, _incident_top_traction_form
    from src.solvers.hcurl_fullspace_dtn import (
        build_fullspace_dtn_action,
        build_fullspace_dtn_carrier_from_surface,
    )
    from src.solvers.hcurl_h2b_m6b_shifted_lu_store import (
        load_h2b_m6b_shifted_lu_patch_store,
    )
    from src.solvers.hcurl_h2b_m6b_shifted_patch_pc import (
        H2BM6BShiftedPatchPC,
        M6BShiftedPCContext,
        build_m6b_outer_mat,
        build_m6b_volume_form,
        compose_m6b_physical_rhs,
        run_m6b_right_fgmres_screen,
    )
    from src.solvers.hcurl_rank_one_mpc_action import build_task037_extra_h1r2_mpc_action

    comm = MPI.COMM_WORLD
    if comm.size != 1:
        raise RuntimeError("M6B online screen is fixed to MPI1")
    run_dir = run_dir.resolve()
    started = time.perf_counter()
    progress_path = run_dir / "m6b_mpi1_progress.jsonl"
    summary_path = run_dir / "m6b_mpi1_worker_summary.json"
    source_start = h2b._light_source()
    status = "gate_failed"
    error: str | None = None
    runtime: dict[str, Any] | None = None
    p6: dict[str, Any] | None = None
    measurement: dict[str, Any] | None = None
    cache_before: Any = None
    cache_after: Any = None
    cache_final: Any = None
    store = None
    physical_action = None
    shifted_action = None
    dtn_action = None
    outer_mat = None
    outer_context = None
    shifted_vec = None
    rhs_vec = None
    base_vec = None
    physical_ufl = None
    shifted_ufl = None
    epsilon0 = None
    abs_epsilon0 = None
    beta0 = None
    epsilon1 = None
    abs_epsilon1 = None
    beta1 = None
    try:
        with progress_path.open("w", encoding="utf-8") as markers:
            stage = h2b._read_json(run_dir / "m6b_stage_summary.json")
            builder = h2b._read_json(run_dir / "m6b_builder_summary.json")
            if (
                stage.get("status") != "measurement_complete"
                or builder.get("status") != "measurement_complete"
                or not h2b._evidence_valid(stage)
                or not h2b._evidence_valid(builder)
                or builder.get("factor_store") is None
            ):
                raise ValueError("M6B online stage/builder authority is incomplete")
            _m6b_emit(markers, "mpi1", "authority_validated", started)
            cfg, mesh_data, function_space, floquet, modes = m6a._production_objects(
                run_dir, mesh_name="m6b_mpi1_mesh"
            )
            p6 = _m6b_p6_identity(mesh_data, function_space, floquet)
            if not _m6b_expected_p6(p6):
                raise ValueError(f"M6B online p6 identity mismatch: {p6}")
            _m6b_emit(markers, "mpi1", "mesh_ready", started)
            _m6b_emit(markers, "mpi1", "space_ready", started)
            _m6b_emit(markers, "mpi1", "floquet_mpc_ready", started)
            cache_dir = run_dir / "jit_cache"
            cache_before = h2b._cache_snapshot(cache_dir)
            physical_ufl, epsilon0, abs_epsilon0, beta0, tag_coverage = build_m6b_volume_form(
                function_space, mesh_data, cfg, beta=0.0
            )
            shifted_ufl, epsilon1, abs_epsilon1, beta1, shifted_tag_coverage = build_m6b_volume_form(
                function_space, mesh_data, cfg, beta=M6B_BETA
            )
            if shifted_tag_coverage != tag_coverage:
                raise ValueError("M6B shared volume material tag coverage changed")
            jit_options = h2b._expected_jit_options(cache_dir)
            physical_action = build_task037_extra_h1r2_mpc_action(
                physical_ufl,
                floquet.mpc,
                task037_extra_h1r2=True,
                jit_options=jit_options,
            )
            shifted_action = build_task037_extra_h1r2_mpc_action(
                shifted_ufl,
                floquet.mpc,
                task037_extra_h1r2=True,
                jit_options=jit_options,
            )
            surface_assemblers = m6a._surface_assemblers(
                function_space, mesh_data, cfg, modes, cache_dir
            )
            incident_form = fem.form(
                _incident_top_traction_form(function_space, mesh_data, cfg),
                jit_options=jit_options,
            )
            cache_after = h2b._cache_snapshot(cache_dir)
            if cache_after != stage.get("forms", {}).get("cache_inventory"):
                raise ValueError("M6B online form/cache identity changed")
            outer_record = _m6b_form_record(
                h2b,
                physical_action,
                cache_dir,
                cfg,
                function_space,
                "outer_volume",
                0.0,
            )
            shifted_record = _m6b_form_record(
                h2b,
                shifted_action,
                cache_dir,
                cfg,
                function_space,
                "shifted_volume",
                M6B_BETA,
            )
            shared_volume_kernel = _m6b_shared_kernel_identity(
                outer_record,
                shifted_record,
                cfg,
                phase="mpi1",
            )
            stage_kernel = stage.get("forms", {}).get("shared_volume_kernel")
            if not _m6b_shared_kernel_valid(stage_kernel, phase="stage"):
                raise ValueError("M6B stage shared volume identity is invalid")
            if any(
                shared_volume_kernel[key] != stage_kernel[key]
                for key in (
                    "operator_identity",
                    "representation",
                    "fixed_physics",
                    "module_name",
                    "ufl_signature",
                    "ufcx_signature",
                )
            ):
                raise ValueError("M6B online shared volume identity differs from stage")
            runtime = _m6b_runtime_identity(
                h2b,
                h2a,
                comm,
                compiler_probe=False,
                compiler=stage["runtime_identity"]["compiler"],
            )
            _m6b_emit(markers, "mpi1", "cache_ready", started)
            store = load_h2b_m6b_shifted_lu_patch_store(
                run_dir / "shifted_lu_store" / "manifest.json",
                task037_extra_m6b=True,
            )
            _m6b_emit(markers, "mpi1", "store_ready", started)
            carrier = build_fullspace_dtn_carrier_from_surface(
                modes,
                surface_assemblers,
                floquet.mpc,
                cfg,
                expected_mode_count=80,
            )
            dtn_action = build_fullspace_dtn_action(carrier, comm=comm)
            outer_mat, outer_context = build_m6b_outer_mat(
                physical_action,
                dtn_action,
                owned_rows=M6B_GLOBAL_ROWS,
                global_rows=M6B_GLOBAL_ROWS,
                comm=comm,
            )
            _m6b_emit(markers, "mpi1", "outer_action_ready", started)
            ownership = tuple(int(value) for value in function_space.dofmap.index_map.local_range)
            projections = tuple(
                __import__(
                    "src.solvers.dtn_port_3d",
                    fromlist=["_incident_projection_onto_top_mode"],
                )._incident_projection_onto_top_mode(mode, cfg)
                for mode in modes
            )
            base_vec = _assemble_mpc_form_vector(incident_form, floquet.mpc)
            rhs_vec = base_vec.duplicate()
            compose_m6b_physical_rhs(dtn_action, base_vec, projections, rhs_vec)
            dual_iterator = __import__(
                "src.solvers.hcurl_canonical_vector_dolfinx",
                fromlist=["iter_canonical_full_fe_dual_packets"],
            ).iter_canonical_full_fe_dual_packets
            rhs_manifest = m6a._write_canonical_role(
                run_dir,
                "mpi1",
                "candidate_physical_rhs_dual",
                dual_iterator(function_space, floquet.mpc, rhs_vec),
                rank=comm.rank,
                mpi_size=comm.size,
                ownership_range=ownership,
                comm=comm,
            )
            _m6b_emit(markers, "mpi1", "rhs_ready", started)
            shifted_vec = shifted_action.output_vector.duplicate()

            def shifted_np(values: np.ndarray) -> np.ndarray:
                with shifted_vec.localForm() as local:
                    local.set(0.0)
                    local.array_w[: values.size] = values
                shifted_vec.ghostUpdate(
                    addv=PETSc.InsertMode.INSERT_VALUES,
                    mode=PETSc.ScatterMode.FORWARD,
                )
                result = shifted_action.mult(shifted_vec)
                values = np.array(
                    result.getArray(readonly=True),
                    dtype=np.complex128,
                    copy=True,
                )
                del result
                return values

            slaves = np.asarray(floquet.mpc.slaves, dtype=np.int64)
            pc_core = H2BM6BShiftedPatchPC(
                store,
                global_row_count=M6B_GLOBAL_ROWS,
                shifted_action=shifted_np,
                slave_identity_rows=slaves,
                task037_extra_m6b=True,
            )
            probe = np.asarray(
                [np.sin(0.0021 * index) + 1j * np.cos(0.0011 * index) for index in range(M6B_GLOBAL_ROWS)],
                dtype=np.complex128,
            )
            first_started = time.perf_counter()
            first_probe, first_probe_measurement = pc_core.apply_with_measurement(probe)
            first_wall_seconds = float(time.perf_counter() - first_started)
            second_started = time.perf_counter()
            second_probe, second_probe_measurement = pc_core.apply_with_measurement(probe)
            second_wall_seconds = float(time.perf_counter() - second_started)

            def probe_record(values: np.ndarray, measurement: Mapping[str, Any], wall: float) -> dict[str, Any]:
                return {
                    "wall_seconds": wall,
                    "hashes": {
                        key: measurement[key]
                        for key in (
                            "rhs_sha256",
                            "correction0_sha256",
                            "action_sha256",
                            "correction_sha256",
                            "residual_sha256",
                        )
                    },
                    "omega": measurement["omega"],
                    "rho_unit": measurement["rho_unit"],
                    "rho_star": measurement["rho_star"],
                    "finite": measurement["finite"],
                    "exact_shifted_action_count": measurement[
                        "exact_shifted_action_count"
                    ],
                    "partition_of_unity_closure_error": measurement[
                        "partition_of_unity_closure_error"
                    ],
                    "correction_bytes": int(np.asarray(values).nbytes),
                }

            first_probe_record = probe_record(
                first_probe, first_probe_measurement, first_wall_seconds
            )
            second_probe_record = probe_record(
                second_probe, second_probe_measurement, second_wall_seconds
            )
            repeat_probe = {
                "first": first_probe_record,
                "second": second_probe_record,
                "identical": bool(
                    first_probe_record["hashes"] == second_probe_record["hashes"]
                    and first_probe_record["omega"] == second_probe_record["omega"]
                    and first_probe_record["rho_unit"] == second_probe_record["rho_unit"]
                    and first_probe_record["rho_star"] == second_probe_record["rho_star"]
                    and first_probe_record["exact_shifted_action_count"]
                    == second_probe_record["exact_shifted_action_count"]
                    and first_probe_record["partition_of_unity_closure_error"]
                    == second_probe_record["partition_of_unity_closure_error"]
                    and first_probe_record["finite"] is True
                    and second_probe_record["finite"] is True
                ),
            }
            del first_probe, second_probe, probe
            pc_context = M6BShiftedPCContext(pc_core)
            screen = run_m6b_right_fgmres_screen(
                outer_mat,
                rhs_vec,
                pc_context=pc_context,
                checkpoint_dir=run_dir,
                operator_context=outer_context,
            )
            _m6b_emit(markers, "mpi1", "screen_ready", started)
            cache_final = h2b._cache_snapshot(cache_dir)
            if cache_before != cache_after or cache_after != cache_final:
                raise ValueError("M6B online cache changed after form construction")
            samples = screen.get("samples")
            if not _m6b_screen_metadata_valid(screen):
                raise ValueError("M6B screen samples are incomplete or nonfinite")
            measurement = {
                "p6": p6,
                "rhs_binding": {
                    "definition": "fresh M6A incident top traction plus fixed outgoing-mode projections",
                    "mode_count": 80,
                    "canonical": rhs_manifest,
                },
                "screen": screen,
                "outer_action_audit": outer_context.audit,
                "volume_action_audit": dict(physical_action.audit),
                "shifted_action_audit": dict(shifted_action.audit),
                "dtn_action_audit": dict(dtn_action.audit),
                "pc_audit": pc_core.audit,
                "material_tag_coverage": tag_coverage,
                "pc_repeat": repeat_probe,
                "m6b_store_audit": store.audit_jsonable(),
                "shared_volume_kernel": shared_volume_kernel,
                "form": {
                    "outer_volume": outer_record,
                    "shifted_volume": shifted_record,
                    "shared_volume_kernel": shared_volume_kernel,
                    "surface": m6a._surface_identity(cache_dir, modes),
                },
                "cache": {
                    "stage": stage.get("forms", {}).get("cache_inventory"),
                    "before": cache_before,
                    "after": cache_after,
                    "final": cache_final,
                    "unchanged": cache_before == cache_after == cache_final,
                },
                "architecture": {
                    "fine_space": "uncondensed_fullspace",
                    "global_matrix": False,
                    "augmented_matrix": False,
                    "static_condensation": False,
                    "trace_slab_pc": False,
                    "explicit_C_materialized_count": 0,
                    "explicit_D_materialized_count": 0,
                    "dtn": True,
                    "pde": False,
                },
                "finite": bool(
                    all(
                        np.isfinite(item["true_relative_residual"])
                        for item in samples.values()
                    )
                ),
            }
            _m6b_emit(markers, "mpi1", "summary_ready", started)
            status = "measurement_complete"
            del surface_assemblers, incident_form, carrier
            gc.collect()
    except h2b._worker_error_types() as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        for item in (rhs_vec, base_vec, shifted_vec):
            if item is not None:
                item.destroy()
        if outer_mat is not None:
            outer_mat.destroy()
        if outer_context is not None:
            outer_context.destroy()
        if physical_action is not None:
            physical_action.destroy()
        if shifted_action is not None:
            shifted_action.destroy()
        del physical_ufl, shifted_ufl, epsilon0, abs_epsilon0, beta0
        del epsilon1, abs_epsilon1, beta1
        gc.collect()
        if dtn_action is not None:
            dtn_action.destroy()
    source_end = h2b._light_source()
    payload = _attach_evidence(
        {
            "schema": M6B_WORKER_SCHEMA,
            "status": status,
            "scope": _m6b_scope(phase="mpi1"),
            "events": list(M6B_ONLINE_EVENTS),
            "p6": p6,
            "measurement": measurement,
            "runtime_identity": runtime,
            "source_at_start": source_start,
            "source_at_end": source_end,
            "error": error,
            "elapsed_wall_seconds": float(time.perf_counter() - started),
        }
    )
    _write_json(summary_path, payload)
    return 0 if status == "measurement_complete" else 1


def _m6b_w2_array_sha256(value: Any) -> str:
    import numpy as np

    array = np.asarray(value)
    digest = hashlib.sha256()
    digest.update(np.asarray(array.shape, dtype=np.int64).tobytes())
    digest.update(str(array.dtype).encode("ascii"))
    digest.update(np.ascontiguousarray(array).tobytes())
    return digest.hexdigest()


def _m6b_w6a_w5_legacy_raw_array_sha256(value: Any) -> str:
    """Hash the raw contiguous bytes used by the frozen W5 compact record."""

    import numpy as np

    array = np.asarray(value)
    return hashlib.sha256(
        np.ascontiguousarray(array).tobytes(order="C")
    ).hexdigest()


def _m6b_w2_cache_record(h2b: Any, path: Path) -> dict[str, Any]:
    entries = h2b._cache_snapshot(path)
    content_entries = [
        {
            "path": item["path"],
            "bytes": int(item["bytes"]),
            "sha256": item["sha256"],
        }
        for item in entries
    ]
    return {
        "entries": content_entries,
        "inventory_sha256": hashlib.sha256(
            h2b._canonical_json({"entries": content_entries})
        ).hexdigest(),
    }


def _m6b_w2_w0_payload_valid(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    source = value.get("source")
    basis = value.get("basis")
    range_projection = value.get("range_projection")
    source_git = source.get("git") if isinstance(source, Mapping) else None
    checkpoints = (
        range_projection.get("checkpoints")
        if isinstance(range_projection, Mapping)
        else None
    )
    if not (
        _evidence_valid(value)
        and value.get("schema") == "task037.m6b.wave_range_az_oracle.v1"
        and value.get("formal_pass") is False
        and value.get("pde_pass") is False
        and value.get("full_pde_qualifies") is False
        and value.get("raw_unchanged") is True
        and isinstance(source, Mapping)
        and source.get("residual_producer_source") == M6B_W2_RESIDUAL_SOURCE_SHA
        and source.get("oracle_execution_source") == M6B_W2_W0_ORACLE_SOURCE_SHA
        and isinstance(source_git, Mapping)
        and source_git.get("branch")
        == "codex/20260806-task37-iterative-extra-development"
        and source_git.get("head") == M6B_W2_W0_ORACLE_SOURCE_SHA
        and source_git.get("upstream") == M6B_W2_W0_ORACLE_SOURCE_SHA
        and source_git.get("ahead") == 0
        and source_git.get("behind") == 0
        and source_git.get("clean") is True
        and isinstance(basis, Mapping)
        and basis.get("manifest_sha256") == M6B_W2_W0_BASIS_MANIFEST_SHA256
        and basis.get("az_column_sha256_aggregate")
        == M6B_W2_W0_AZ_COLUMN_SHA256_AGGREGATE
        and isinstance(checkpoints, Mapping)
        and set(checkpoints) == {
            str(item) for item in M6B_W2_FIXED_RESIDUAL_ITERATIONS
        }
    ):
        return False
    return all(
        isinstance(checkpoints[key], Mapping)
        and checkpoints[key].get("iteration") == int(key)
        and checkpoints[key].get("finite") is True
        and _finite_number(checkpoints[key].get("rho_range"))
        and checkpoints[key]["rho_range"] == M6B_W2_W0_RANGE_RHO_AUTHORITY[key]
        for key in checkpoints
    )


def _m6b_w2_w0_authority_record(path: Path) -> dict[str, Any]:
    path = Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"M6B W0 authority file is missing: {path}")
    file_sha256 = _sha256_file(path)
    if file_sha256 != M6B_W2_W0_OUTPUT_SHA256:
        raise ValueError("M6B W0 authority file SHA differs")
    payload = _read_json(path)
    if not _m6b_w2_w0_payload_valid(payload):
        raise ValueError("M6B W0 authority payload is not closed")
    return {
        "file_artifact": {
            "path": str(path),
            "present": True,
            "bytes": int(path.stat().st_size),
            "sha256": file_sha256,
        },
        "schema": payload["schema"],
        "evidence_sha256": payload["evidence_sha256"],
        "residual_producer_source": payload["source"][
            "residual_producer_source"
        ],
        "oracle_execution_source": payload["source"]["oracle_execution_source"],
        "basis_manifest_sha256": payload["basis"]["manifest_sha256"],
        "az_column_sha256_aggregate": payload["basis"][
            "az_column_sha256_aggregate"
        ],
        "range_rho": {
            key: payload["range_projection"]["checkpoints"][key]["rho_range"]
            for key in sorted(payload["range_projection"]["checkpoints"])
        },
    }


def _m6b_w2_authority_record(
    factor_authority_dir: Path,
    wave_authority_dir: Path,
    jit_cache_source: Path,
    w0_authority_file: Path,
    *,
    expected_beta: float = M6B_W2_SHIFTED_BETA,
    factor_manifest_sha256: str = M6B_W2_FACTOR_MANIFEST_SHA256,
    factor_source_sha: str = M6B_W2_RESIDUAL_SOURCE_SHA,
) -> dict[str, Any]:
    if expected_beta not in (M6B_W2_SHIFTED_BETA, M6B_W3_BETA05):
        raise ValueError("M6B factor authority beta is not fixed")
    if not _m6b_w2_sha_valid(factor_manifest_sha256):
        raise ValueError("M6B factor manifest SHA is invalid")
    if not _m6b_w2_source_sha_valid(factor_source_sha):
        raise ValueError("M6B factor source SHA is invalid")
    factor_manifest = factor_authority_dir / "shifted_lu_store" / "manifest.json"
    wave_manifest = wave_authority_dir / "sparse_range_store" / "manifest.json"
    factor_summary = factor_authority_dir / "m6b_builder_summary.json"
    wave_summary = wave_authority_dir / "w1_builder_summary.json"
    required = (factor_manifest, wave_manifest, factor_summary, wave_summary)
    if any(not path.is_file() for path in required) or not jit_cache_source.is_dir():
        raise FileNotFoundError("M6B W2 authority artifact is missing")
    w0_authority = _m6b_w2_w0_authority_record(w0_authority_file)
    if _sha256_file(factor_manifest) != factor_manifest_sha256:
        raise ValueError("M6B W2 factor manifest authority differs")
    if _sha256_file(wave_manifest) != M6B_W2_WAVE_MANIFEST_SHA256:
        raise ValueError("M6B W2 sparse range manifest authority differs")
    factor = _read_json(factor_summary)
    wave = _read_json(wave_summary)
    factor_payload = _read_json(factor_manifest)
    wave_payload = _read_json(wave_manifest)
    if not (
        _evidence_valid(factor)
        and _evidence_valid(wave)
        and _m6b_w2_factor_manifest_valid(
            factor_payload, expected_beta=expected_beta
        )
        and wave_payload.get("schema")
        == "task037.extra.m6b.sparse-range-store.v2"
        and wave_payload.get("global_rows") == M6B_GLOBAL_ROWS
        and wave_payload.get("columns") == 75
        and wave_payload.get("az_v_retained") is False
        and wave_payload.get("retained_az_bytes") == 0
    ):
        raise ValueError("M6B W2 store schema or evidence is not closed")
    factor_start = factor.get("source_at_start")
    factor_end = factor.get("source_at_end")
    wave_source = wave.get("source")
    if not (
        isinstance(factor_start, Mapping)
        and isinstance(factor_end, Mapping)
        and factor_start.get("source_commit_full_sha") == factor_source_sha
        and factor_end.get("source_commit_full_sha") == factor_source_sha
        and factor_start.get("tracked_source_dirty") is False
        and factor_end.get("tracked_source_dirty") is False
        and isinstance(wave_source, Mapping)
        and wave_source.get("source_commit_full_sha") == M6B_W2_WAVE_SOURCE_SHA
        and wave_source.get("source_worktree_dirty") is False
        and wave.get("basis_manifest_sha256") == M6B_W2_W0_BASIS_MANIFEST_SHA256
        and isinstance(wave.get("carrier_audit"), Mapping)
        and wave["carrier_audit"].get("az_column_sha256_aggregate")
        == M6B_W2_W0_AZ_COLUMN_SHA256_AGGREGATE
        and wave["carrier_audit"].get("az_v_retained") is False
        and wave["carrier_audit"].get("retained_az_bytes") == 0
    ):
        raise ValueError("M6B W2 authority provenance is not closed")
    return {
        "factor_manifest": _artifact(
            factor_authority_dir, "shifted_lu_store/manifest.json"
        ),
        "wave_manifest": _artifact(
            wave_authority_dir, "sparse_range_store/manifest.json"
        ),
        "factor_builder_summary": _artifact(
            factor_authority_dir, "m6b_builder_summary.json"
        ),
        "wave_builder_summary": _artifact(
            wave_authority_dir, "w1_builder_summary.json"
        ),
        "factor_source_sha": factor_source_sha,
        "factor_beta": expected_beta,
        "wave_source_sha": M6B_W2_WAVE_SOURCE_SHA,
        "w0_authority": w0_authority,
        "w0_output_sha256": M6B_W2_W0_OUTPUT_SHA256,
        "basis_manifest_sha256": wave["basis_manifest_sha256"],
        "az_column_sha256_aggregate": wave["carrier_audit"][
            "az_column_sha256_aggregate"
        ],
        "factor_compiler": factor.get("runtime_identity", {}).get("compiler"),
        "jit_source": str(jit_cache_source),
    }


def _m6b_w2_factor_manifest_valid(
    value: Any, *, expected_beta: float = M6B_W2_SHIFTED_BETA
) -> bool:
    """Validate one of the two fixed shifted-factor manifest contracts."""

    if expected_beta not in (M6B_W2_SHIFTED_BETA, M6B_W3_BETA05):
        return False

    if not isinstance(value, Mapping):
        return False
    audit = value.get("audit")
    if not isinstance(audit, Mapping):
        return False
    materialization = audit.get("materialization_identity")
    if not isinstance(materialization, Mapping):
        return False
    return (
        value.get("schema") == "task037.extra.h2b.m6b.shifted-lu-store.v1"
        and value.get("beta") == expected_beta
        and audit.get("schema")
        == "task037.extra.h2b.m6b.shifted-lu-store.v1"
        and audit.get("beta") == expected_beta
        and audit.get("factor_count") == M6B_FACTOR_COUNT
        and audit.get("cell_count") == M6B_GLOBAL_CELLS
        and audit.get("factor_order") == 882
        and audit.get("factor_reuse_count") == M6B_FACTOR_REUSE
        and audit.get("factor_payload_bytes") == M6B_FACTOR_PAYLOAD_BYTES
        and audit.get("retained_total_gate") is True
        and all(materialization.get(key) is False for key in (
            "global_constraint_matrix",
            "global_matrix",
            "patch_matrices",
            "per_cell_factor",
            "schur",
            "slab_factor",
            "static_condensation",
            "trace_slab",
        ))
    )


def _run_m6b_w2_diagnostic(
    run_dir: Path,
    factor_authority_dir: Path,
    wave_authority_dir: Path,
    jit_cache_source: Path,
    expected_source_sha: str,
    w0_authority_file: Path,
    *,
    projected: bool = False,
    screen: bool = False,
    shifted_beta: float = M6B_W2_SHIFTED_BETA,
    factor_manifest_sha256: str = M6B_W2_FACTOR_MANIFEST_SHA256,
    factor_source_sha: str = M6B_W2_RESIDUAL_SOURCE_SHA,
    solver: str = "fgmres",
    initial_solution: Any | None = None,
    continuation_authority: Mapping[str, Any] | None = None,
) -> int:
    import gc
    import shutil
    import time

    import numpy as np
    from dolfinx import fem
    from mpi4py import MPI
    from petsc4py import PETSc
    import ufl

    h2b = __import__("benchmarks.run_task037_extra_h2b", fromlist=["*"])
    h2a = h2b._lazy_h2a()
    m6a = __import__("benchmarks.run_task037_extra_m6", fromlist=["*"])
    from src.solvers.hcurl_fullspace_dtn import (
        build_fullspace_dtn_action,
        build_fullspace_dtn_carrier_from_surface,
    )
    from src.solvers.hcurl_h2b_m6b_shifted_lu_store import (
        load_h2b_m6b_shifted_lu_patch_store,
    )
    from src.solvers.hcurl_h2b_m6b_shifted_patch_pc import (
        H2BM6BProjectedRangePC,
        H2BM6BShiftedPatchPC,
        H2BM6BShiftedRangePC,
        M6BNumpyOuterActionBridge,
        build_m6b_outer_mat,
        build_m6b_volume_form,
        compose_m6b_physical_rhs,
        run_m6b_disk_backed_right_fgmres_screen,
    )
    from src.solvers.dtn_port_3d import (
        _assemble_mpc_form_vector,
        _incident_projection_onto_top_mode,
        _incident_top_traction_form,
    )
    from src.solvers.hcurl_m6b_sparse_range import (
        load_sparse_m6b_range_carrier,
    )
    from src.solvers.hcurl_rank_one_mpc_action import (
        build_task037_extra_h1r2_mpc_action,
    )

    run_dir = Path(run_dir).resolve()
    factor_authority_dir = Path(factor_authority_dir).resolve()
    wave_authority_dir = Path(wave_authority_dir).resolve()
    jit_cache_source = Path(jit_cache_source).resolve()
    w0_authority_file = Path(w0_authority_file).resolve()
    if solver not in {"fgmres", "fbcgs", "disk_fgmres", "disk_fgmres_restart"}:
        raise ValueError("M6B screen solver is not fixed")
    if solver == "fbcgs" and (
        not screen or not projected or shifted_beta != M6B_W4_BETA
    ):
        raise ValueError("M6B W4 FBCGS requires the fixed beta=1 projected screen")
    if solver in {"disk_fgmres", "disk_fgmres_restart"} and (
        not screen or not projected or shifted_beta != M6B_W5_BETA
    ):
        raise ValueError(
            "M6B W5 disk FGMRES requires the fixed beta=1 projected screen"
        )
    if solver == "disk_fgmres_restart" and (
        initial_solution is None
        or not isinstance(initial_solution, np.ndarray)
        or initial_solution.size == 0
        or not isinstance(continuation_authority, dict)
    ):
        raise ValueError("M6B W7-S1 requires the frozen W5 continuation authority")
    if screen and not projected:
        raise ValueError("M6B W3 screen requires the projected range PC")
    if shifted_beta not in (M6B_W2_SHIFTED_BETA, M6B_W3_BETA05):
        raise ValueError("M6B shifted screen beta is not fixed")
    if not screen and shifted_beta != M6B_W2_SHIFTED_BETA:
        raise ValueError("M6B W2 and W2R remain fixed at beta=1")
    if run_dir.exists():
        raise FileExistsError(f"M6B W2 refuses an existing run directory: {run_dir}")
    if MPI.COMM_WORLD.size != 1:
        raise RuntimeError("M6B W2 diagnostic is fixed to MPI1")
    if not _m6b_w2_source_sha_valid(expected_source_sha):
        raise ValueError("M6B W2 expected source SHA is invalid")
    authority = _m6b_w2_authority_record(
        factor_authority_dir,
        wave_authority_dir,
        jit_cache_source,
        w0_authority_file,
        expected_beta=shifted_beta,
        factor_manifest_sha256=factor_manifest_sha256,
        factor_source_sha=factor_source_sha,
    )
    w2r_negative_authority = _m6b_w2r_old_negative_record() if (projected or screen) else None
    w2r_positive_authority = _m6b_w2r_positive_record() if screen else None
    run_dir.mkdir(parents=True)
    cache_dir = run_dir / "jit_cache"
    shutil.copytree(jit_cache_source, cache_dir)
    started = time.perf_counter()
    if screen:
        if solver == "disk_fgmres_restart":
            screen_schema = M6B_W7_S1_SCHEMA
            phase_name = M6B_W7_S1_PHASE
            progress_path = run_dir / "m6b_w7_s1_progress.jsonl"
            summary_path = run_dir / "m6b_w7_s1_summary.json"
        elif solver == "disk_fgmres":
            screen_schema = M6B_W5_SCHEMA
            phase_name = M6B_W5_PHASE
            progress_path = run_dir / "m6b_w5_progress.jsonl"
            summary_path = run_dir / "m6b_w5_summary.json"
        elif solver == "fbcgs":
            screen_schema = M6B_W4_SCHEMA
            phase_name = M6B_W4_PHASE
            progress_path = run_dir / "m6b_w4_progress.jsonl"
            summary_path = run_dir / "m6b_w4_summary.json"
        elif shifted_beta == M6B_W3_BETA:
            screen_schema = M6B_W3_SCHEMA
            phase_name = M6B_W3_PHASE
            progress_path = run_dir / "m6b_w3_progress.jsonl"
            summary_path = run_dir / "m6b_w3_summary.json"
        else:
            screen_schema = M6B_W3_BETA05_SCHEMA
            phase_name = M6B_W3_BETA05_PHASE
            progress_path = run_dir / "m6b_w3_progress.jsonl"
            summary_path = run_dir / "m6b_w3_summary.json"
        progress_schema = f"{screen_schema}.progress.v1"
    elif projected:
        progress_path = run_dir / "m6b_w2r_progress.jsonl"
        summary_path = run_dir / "m6b_w2r_summary.json"
        progress_schema = f"{M6B_W2R_SCHEMA}.progress.v1"
        phase_name = "w2r_diagnostic"
    else:
        progress_path = run_dir / "m6b_w2_progress.jsonl"
        summary_path = run_dir / "m6b_w2_summary.json"
        progress_schema = f"{M6B_W2_SCHEMA}.progress.v1"
        phase_name = "w2_diagnostic"
    source_start = h2b._light_source()
    status = "gate_failed"
    error: str | None = None
    measurements: dict[str, Any] = {}
    runtime: dict[str, Any] | None = None
    p6: dict[str, Any] | None = None
    cache_before: dict[str, Any] | None = None
    cache_after: dict[str, Any] | None = None
    cache_final: dict[str, Any] | None = None
    source_cache_before: dict[str, Any] | None = None
    source_cache_after: dict[str, Any] | None = None
    source_cache_final: dict[str, Any] | None = None
    store = None
    range_carrier = None
    local_pc = None
    outer_mat = None
    outer_context = None
    outer_bridge = None
    physical_action = None
    shifted_action = None
    adjoint_action = None
    dtn_action = None
    shifted_vec = None
    template = None
    physical_ufl = shifted_ufl = adjoint_ufl = None
    epsilon0 = abs_epsilon0 = beta0 = None
    epsilon1 = abs_epsilon1 = beta1 = None
    base_vec = rhs_vec = None
    incident_form = None
    rhs_manifest = None
    screen_result = None
    shared_volume_kernel = None
    outer_record = None
    shifted_record = None

    def emit(event: str, **extra: Any) -> None:
        payload = {
            "schema": progress_schema,
            "phase": phase_name,
            "event": event,
            "elapsed_wall_seconds": float(time.perf_counter() - started),
            **extra,
        }
        with progress_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
            stream.flush()
        print(json.dumps(payload, sort_keys=True), flush=True)

    try:
        if not _m6b_w2_source_identity_valid(source_start, expected_source_sha):
            raise ValueError("M6B W2 execution source is not the expected clean source")
        source_cache_before = _m6b_w2_cache_record(h2b, jit_cache_source)
        if source_cache_before["inventory_sha256"] != M6B_W2_JIT_INVENTORY_SHA256:
            raise ValueError("M6B W2 JIT source inventory authority differs")
        cache_before = _m6b_w2_cache_record(h2b, cache_dir)
        if (
            not cache_before["entries"]
            or cache_before["inventory_sha256"]
            != source_cache_before["inventory_sha256"]
        ):
            raise ValueError("M6B W2 copied JIT cache differs from source")
        emit("authority_validated", **authority)
        mesh_name = (
            "m6b_w7_s1_mesh"
            if solver == "disk_fgmres_restart"
            else "m6b_w5_mesh"
            if solver == "disk_fgmres"
            else "m6b_w4_mesh"
            if solver == "fbcgs"
            else "m6b_w2r_mesh"
            if projected
            else "m6b_w2_mesh"
        )
        cfg, mesh_data, function_space, floquet, modes = m6a._production_objects(
            run_dir, mesh_name=mesh_name
        )
        p6 = _m6b_p6_identity(mesh_data, function_space, floquet)
        if not _m6b_expected_p6(p6):
            raise ValueError("M6B W2 p6 identity differs")
        if not isinstance(authority["factor_compiler"], Mapping):
            raise ValueError("M6B W2 factor compiler identity is missing")
        runtime = _m6b_runtime_identity(
            h2b,
            h2a,
            MPI.COMM_WORLD,
            compiler_probe=False,
            compiler=authority["factor_compiler"],
        )
        emit("mesh_ready", p6=p6)
        emit("space_ready")
        emit("floquet_mpc_ready")
        jit_options = h2b._expected_jit_options(cache_dir)
        physical_ufl, epsilon0, abs_epsilon0, beta0, tag_coverage = build_m6b_volume_form(
            function_space, mesh_data, cfg, beta=0.0
        )
        shifted_ufl, epsilon1, abs_epsilon1, beta1, shifted_coverage = build_m6b_volume_form(
            function_space, mesh_data, cfg, beta=shifted_beta
        )
        if shifted_coverage != tag_coverage:
            raise ValueError("M6B W2 material tag coverage changed")
        physical_action = build_task037_extra_h1r2_mpc_action(
            physical_ufl, floquet.mpc, task037_extra_h1r2=True, jit_options=jit_options
        )
        shifted_action = build_task037_extra_h1r2_mpc_action(
            shifted_ufl, floquet.mpc, task037_extra_h1r2=True, jit_options=jit_options
        )
        adjoint_ufl = ufl.adjoint(physical_ufl)
        adjoint_action = build_task037_extra_h1r2_mpc_action(
            adjoint_ufl, floquet.mpc, task037_extra_h1r2=True, jit_options=jit_options
        )
        surface_assemblers = m6a._surface_assemblers(
            function_space, mesh_data, cfg, modes, cache_dir
        )
        if screen:
            incident_form = fem.form(
                _incident_top_traction_form(function_space, mesh_data, cfg),
                jit_options=jit_options,
            )
        cache_after = _m6b_w2_cache_record(h2b, cache_dir)
        source_cache_after = _m6b_w2_cache_record(h2b, jit_cache_source)
        if (
            cache_after["inventory_sha256"] != cache_before["inventory_sha256"]
            or source_cache_after["inventory_sha256"]
            != source_cache_before["inventory_sha256"]
        ):
            raise ValueError("M6B W2 form construction changed the frozen cache")
        emit("cache_ready", inventory_sha256=cache_after["inventory_sha256"])
        carrier = build_fullspace_dtn_carrier_from_surface(
            modes, surface_assemblers, floquet.mpc, cfg, expected_mode_count=80
        )
        dtn_action = build_fullspace_dtn_action(carrier, comm=MPI.COMM_WORLD)
        outer_mat, outer_context = build_m6b_outer_mat(
            physical_action,
            dtn_action,
            owned_rows=M6B_GLOBAL_ROWS,
            global_rows=M6B_GLOBAL_ROWS,
            comm=MPI.COMM_WORLD,
            volume_hermitian_action=adjoint_action,
        )
        template = outer_mat.createVecRight()
        outer_bridge = M6BNumpyOuterActionBridge(outer_context, template)

        def outer_numpy(values: np.ndarray, *, hermitian: bool = False) -> np.ndarray:
            return (
                outer_bridge.apply_hermitian(values)
                if hermitian
                else outer_bridge.apply(values)
            )

        shifted_vec = shifted_action.output_vector.duplicate()

        def shifted_numpy(values: np.ndarray) -> np.ndarray:
            with shifted_vec.localForm() as local:
                local.set(0.0)
                local.array_w[: values.size] = values
            shifted_vec.ghostUpdate(
                addv=PETSc.InsertMode.INSERT_VALUES,
                mode=PETSc.ScatterMode.FORWARD,
            )
            result = shifted_action.mult(shifted_vec)
            return np.array(
                result.getArray(readonly=True), dtype=np.complex128, copy=True
            )

        store = load_h2b_m6b_shifted_lu_patch_store(
            factor_authority_dir / "shifted_lu_store" / "manifest.json",
            task037_extra_m6b=True,
        )
        local_pc = H2BM6BShiftedPatchPC(
            store,
            global_row_count=M6B_GLOBAL_ROWS,
            shifted_action=shifted_numpy,
            slave_identity_rows=np.asarray(floquet.mpc.slaves, dtype=np.int64),
            task037_extra_m6b=True,
        )
        range_carrier = load_sparse_m6b_range_carrier(
            wave_authority_dir / "sparse_range_store" / "manifest.json",
            comm=MPI.COMM_WORLD,
            hermitian_action=lambda values: outer_numpy(values, hermitian=True),
        )
        if projected:
            w2_pc = H2BM6BProjectedRangePC(
                local_pc,
                range_carrier,
                lambda values: outer_numpy(values),
                global_row_count=M6B_GLOBAL_ROWS,
                task037_extra_m6b=True,
                expected_local_beta=shifted_beta,
            )
        else:
            w2_pc = H2BM6BShiftedRangePC(
                local_pc,
                range_carrier,
                lambda values: outer_numpy(values),
                global_row_count=M6B_GLOBAL_ROWS,
                task037_extra_m6b=True,
            )
        emit("outer_and_carriers_ready", range_audit=range_carrier.audit)
        if screen:
            outer_record = _m6b_form_record(
                h2b,
                physical_action,
                cache_dir,
                cfg,
                function_space,
                "outer_volume",
                0.0,
            )
            shifted_record = _m6b_form_record(
                h2b,
                shifted_action,
                cache_dir,
                cfg,
                function_space,
                "shifted_volume",
                shifted_beta,
            )
            shared_volume_kernel = _m6b_shared_kernel_identity(
                outer_record,
                shifted_record,
                cfg,
                phase="mpi1",
                shifted_beta=shifted_beta,
            )
            if not (
                _m6b_shared_kernel_valid(
                    shared_volume_kernel,
                    phase="mpi1",
                    shifted_beta=shifted_beta,
                )
                and _m6b_form_records_bound(
                    outer_record,
                    shifted_record,
                    shared_volume_kernel,
                    phase="mpi1",
                    shifted_beta=shifted_beta,
                )
            ):
                raise ValueError("M6B W3 shared volume form binding is invalid")
            base_vec = _assemble_mpc_form_vector(incident_form, floquet.mpc)
            rhs_vec = base_vec.duplicate()
            projections = tuple(
                _incident_projection_onto_top_mode(mode, cfg) for mode in modes
            )
            compose_m6b_physical_rhs(dtn_action, base_vec, projections, rhs_vec)
            emit("rhs_ready", mode_count=80)
            ownership = tuple(
                int(value) for value in function_space.dofmap.index_map.local_range
            )
            dual_iterator = __import__(
                "src.solvers.hcurl_canonical_vector_dolfinx",
                fromlist=["iter_canonical_full_fe_dual_packets"],
            ).iter_canonical_full_fe_dual_packets
            rhs_manifest = m6a._write_canonical_role(
                run_dir,
                "mpi1",
                "candidate_physical_rhs_dual",
                dual_iterator(function_space, floquet.mpc, rhs_vec),
                rank=MPI.COMM_WORLD.rank,
                mpi_size=MPI.COMM_WORLD.size,
                ownership_range=ownership,
                comm=MPI.COMM_WORLD,
            )
            emit(
                "screen_started",
                solver=solver,
                ksp_iterations=(
                    list(M6B_W4_KSP_ITERATIONS)
                    if solver == "fbcgs"
                    else []
                    if solver in {"disk_fgmres", "disk_fgmres_restart"}
                    else list(M6B_SCREEN_ITERATIONS)
                ),
                pc_apply_budgets=(
                    list(M6B_W4_PC_APPLY_BUDGETS)
                    if solver == "fbcgs"
                    else list(M6B_SCREEN_ITERATIONS)
                ),
                checkpoint_axis=(
                    "pc_apply_budget"
                    if solver == "fbcgs"
                    else "local_cycle_iteration"
                    if solver == "disk_fgmres_restart"
                    else "krylov_iteration"
                    if solver == "disk_fgmres"
                    else "ksp_iteration"
                ),
                cumulative_checkpoint_iterations=(
                    list(M6B_W7_S1_CUMULATIVE_ITERATIONS)
                    if solver == "disk_fgmres_restart"
                    else []
                ),
                fixed_screen=True,
            )
            if solver in {"disk_fgmres", "disk_fgmres_restart"}:
                rhs_numpy = np.array(
                    rhs_vec.getArray(readonly=True), dtype=np.complex128, copy=True
                )
                if solver == "disk_fgmres_restart":
                    if not isinstance(continuation_authority, dict):
                        raise ValueError("M6B W7-S1 continuation payload is missing")
                    continuation_rhs = continuation_authority.pop("frozen_rhs", None)
                    continuation_outer_action = continuation_authority.pop(
                        "frozen_outer_action", None
                    )
                    continuation_residual = continuation_authority.pop(
                        "frozen_residual", None
                    )
                    if not isinstance(continuation_rhs, np.ndarray):
                        raise ValueError("M6B W7-S1 frozen RHS is missing")
                    if (
                        continuation_rhs.shape != rhs_numpy.shape
                        or continuation_rhs.dtype != np.dtype(np.complex128)
                        or not np.array_equal(continuation_rhs, rhs_numpy)
                    ):
                        raise ValueError("M6B W7-S1 RHS differs from frozen W5")
                    if not isinstance(continuation_outer_action, np.ndarray) or not isinstance(
                        continuation_residual, np.ndarray
                    ):
                        raise ValueError("M6B W7-S1 frozen action/residual is missing")
                    initial_action = outer_numpy(initial_solution)
                    repeated_action = outer_numpy(initial_solution)
                    initial_residual = rhs_numpy - initial_action
                    denominator = max(
                        np.linalg.norm(continuation_outer_action),
                        np.finfo(float).tiny,
                    )
                    action_repeat_error = float(
                        np.linalg.norm(repeated_action - initial_action) / denominator
                    )
                    action_frozen_error = float(
                        np.linalg.norm(initial_action - continuation_outer_action)
                        / denominator
                    )
                    residual_frozen_error = float(
                        np.linalg.norm(initial_residual - continuation_residual)
                        / max(np.linalg.norm(continuation_residual), np.finfo(float).tiny)
                    )
                    initial_rho = float(
                        np.linalg.norm(initial_residual)
                        / max(np.linalg.norm(rhs_numpy), np.finfo(float).tiny)
                    )
                    if (
                        not np.all(np.isfinite(initial_action))
                        or not np.all(np.isfinite(repeated_action))
                        or not np.all(np.isfinite(initial_residual))
                        or not np.all(np.isfinite(continuation_outer_action))
                        or not np.all(np.isfinite(continuation_residual))
                        or not math.isfinite(initial_rho)
                        or not math.isfinite(action_repeat_error)
                        or not math.isfinite(action_frozen_error)
                        or not math.isfinite(residual_frozen_error)
                        or action_repeat_error > 1.0e-15
                        or action_frozen_error > 1.0e-12
                        or residual_frozen_error > 1.0e-12
                        or abs(initial_rho - M6B_W7_S1_INITIAL_RHO) > 1.0e-12
                    ):
                        raise ValueError("M6B W7-S1 initial residual authority differs")
                    continuation_authority = dict(continuation_authority)
                    continuation_authority["initial_check"] = {
                        "initial_solution_provided": True,
                        "precheck_action_count": 2,
                        "core_initial_action_count": 1,
                        "rhs_equal_to_frozen_w5": True,
                        "initial_true_relative_residual": initial_rho,
                        "frozen_true_relative_residual": M6B_W7_S1_INITIAL_RHO,
                        "repeat_relative_error": action_repeat_error,
                        "frozen_action_relative_error": action_frozen_error,
                        "frozen_residual_relative_error": residual_frozen_error,
                        "rho_absolute_error": abs(
                            initial_rho - M6B_W7_S1_INITIAL_RHO
                        ),
                        "finite": True,
                    }
                    del initial_action, repeated_action, initial_residual
                    continuation_rhs = None
                    continuation_outer_action = None
                    continuation_residual = None
                disk_pc_apply_count = 0

                def disk_right_pc(values: np.ndarray) -> np.ndarray:
                    nonlocal disk_pc_apply_count
                    result = w2_pc.apply(values)
                    disk_pc_apply_count += 1
                    if disk_pc_apply_count % 10 == 0:
                        emit(
                            "krylov_progress",
                            pc_apply_count=disk_pc_apply_count,
                            completed_pc_applies=disk_pc_apply_count,
                            max_pc_applies=200,
                        )
                    return result

                screen_result = run_m6b_disk_backed_right_fgmres_screen(
                    outer_numpy,
                    disk_right_pc,
                    rhs_numpy,
                    checkpoint_dir=run_dir,
                    scratch_dir=run_dir / "krylov_scratch",
                    initial_solution=initial_solution
                    if solver == "disk_fgmres_restart"
                    else None,
                    schema=(
                        M6B_W7_S1_CORE_SCHEMA
                        if solver == "disk_fgmres_restart"
                        else M6B_W5_CORE_SCHEMA
                    ),
                    observer=lambda metadata: emit("checkpoint_ready", **metadata),
                )
                if solver == "disk_fgmres_restart":
                    screen_result["cycle"] = "fixed_one_200_step_restart_cycle"
                    screen_result["checkpoint_axis"] = "local_cycle_iteration"
                    screen_result["cumulative_checkpoint_iterations"] = list(
                        M6B_W7_S1_CUMULATIVE_ITERATIONS
                    )
                    screen_result["initial_solution_provided"] = True
                    screen_result["continuation_authority"] = continuation_authority
                    for local, cumulative in zip(
                        M6B_W7_S1_LOCAL_ITERATIONS,
                        M6B_W7_S1_CUMULATIVE_ITERATIONS,
                    ):
                        screen_result["samples"][str(local)].update(
                            {
                                "local_iteration": local,
                                "cumulative_iteration": cumulative,
                                "checkpoint_axis": "local_cycle_iteration",
                            }
                        )
                    initial_solution = None
                del rhs_numpy
            else:
                pc_context, screen_result = _m6b_w3_screen_orchestration(
                    projected_pc=w2_pc,
                    outer_mat=outer_mat,
                    outer_context=outer_context,
                    rhs_vec=rhs_vec,
                    checkpoint_dir=run_dir,
                    solver=solver,
                    checkpoint_observer=lambda metadata: emit(
                        "checkpoint_ready", **metadata
                    ),
                )
            samples = screen_result.get("samples")
            metadata_valid = (
                _m6b_w4_screen_metadata_valid(screen_result)
                if solver == "fbcgs"
                else _m6b_w5_screen_metadata_valid(screen_result)
                if solver == "disk_fgmres"
                else _m6b_w7_s1_screen_metadata_valid(screen_result)
                if solver == "disk_fgmres_restart"
                else _m6b_screen_metadata_valid(screen_result)
            )
            if not metadata_valid:
                raise ValueError("M6B screen samples are incomplete or nonfinite")
            gate = (
                _m6b_w7_s1_numeric_gate(samples)
                if solver == "disk_fgmres_restart"
                else _m6b_w3_numeric_gate(samples)
            )
            screen_result["numeric_gate"] = gate
            measurements["screen"] = {
                "screen": screen_result,
                "screen_gate": gate,
                "rhs_binding": {
                    "definition": (
                        "fresh M6A incident top traction plus fixed outgoing-mode projections"
                    ),
                    "mode_count": 80,
                    "canonical": rhs_manifest,
                },
                "outer_action_audit": _m6b_screen_audit_jsonable(
                    h2a, outer_context.audit
                ),
                "volume_action_audit": _m6b_screen_audit_jsonable(
                    h2a, physical_action.audit
                ),
                "shifted_action_audit": _m6b_screen_audit_jsonable(
                    h2a, shifted_action.audit
                ),
                "dtn_action_audit": _m6b_screen_audit_jsonable(
                    h2a, dtn_action.audit
                ),
                "pc_audit": _m6b_screen_audit_jsonable(h2a, w2_pc.audit),
                "outer_numpy_bridge": _m6b_screen_audit_jsonable(
                    h2a, outer_bridge.audit
                ),
                "range_store_audit": _m6b_screen_audit_jsonable(
                    h2a, range_carrier.audit
                ),
                "m6b_store_audit": store.audit_jsonable(),
                "material_tag_coverage": tag_coverage,
                "shared_volume_kernel": shared_volume_kernel,
                "form": {
                    "outer_volume": outer_record,
                    "shifted_volume": shifted_record,
                    "shared_volume_kernel": shared_volume_kernel,
                    "surface": m6a._surface_identity(cache_dir, modes),
                },
                "architecture": {
                    "fine_space": "uncondensed_fullspace",
                    "global_matrix": False,
                    "augmented_matrix": False,
                    "static_condensation": False,
                    "trace_slab_pc": False,
                    "schur": False,
                    "explicit_C_materialized_count": 0,
                    "explicit_D_materialized_count": 0,
                    "pde": False,
                },
            }
            status = "screen_complete" if gate["pass"] else "gate_failed"
            emit("screen_ready", gate=gate, iterations=screen_result["iterations"])
        else:
            for key in ("20", "100", "150", "200"):
                residual_path = factor_authority_dir / f"m6b_iter{key}_residual.npy"
                residual = np.load(residual_path, allow_pickle=False)
                if (
                    residual.dtype != np.dtype(np.complex128)
                    or residual.shape != (M6B_GLOBAL_ROWS,)
                    or not np.all(np.isfinite(residual))
                    or _m6b_w2_array_sha256(residual) != M6B_W2_RESIDUAL_ARRAY_SHAS[key]
                ):
                    raise ValueError(f"M6B W2 residual authority is invalid: {key}")
                first, first_measurement = w2_pc.apply_with_measurement(residual)
                second, second_measurement = w2_pc.apply_with_measurement(residual)
                record = dict(first_measurement)
                record.update(
                    {
                        "iteration": int(key),
                        "residual_array_sha256": M6B_W2_RESIDUAL_ARRAY_SHAS[key],
                        "residual_artifact": {
                            **_artifact(
                                factor_authority_dir,
                                f"m6b_iter{key}_residual.npy",
                            ),
                            "absolute_path": str(residual_path),
                        },
                        "correction_sha256": first_measurement["final_correction_sha256"],
                        "repeat_correction_sha256": second_measurement[
                            "final_correction_sha256"
                        ],
                        "repeat_identical": bool(
                            np.array_equal(first, second)
                            and first_measurement == second_measurement
                        ),
                    }
                )
                measurements[key] = record
                del residual, first, second, first_measurement, second_measurement
                event_values = {"rho_range_only": record["rho_range_only"]}
                event_values["rho_projected" if projected else "rho_composed"] = record[
                    "rho_projected" if projected else "rho_composed"
                ]
                emit("residual_complete", iteration=int(key), **event_values)
            gate = _m6b_w2r_gate(measurements) if projected else _m6b_w2_gate(measurements)
        cache_final = _m6b_w2_cache_record(h2b, cache_dir)
        source_cache_final = _m6b_w2_cache_record(h2b, jit_cache_source)
        if (
            cache_final != cache_after
            or source_cache_final["inventory_sha256"]
            != source_cache_before["inventory_sha256"]
        ):
            raise ValueError("M6B W2 cache changed after diagnostic actions")
        status = (
            ("screen_complete" if screen else "diagnostic_complete")
            if gate["pass"]
            else "gate_failed"
        )
        emit("summary_ready", status=status, gate=gate)
    except FloatingPointError as exc:
        error = f"{type(exc).__name__}: {exc}"
    except h2b._worker_error_types() as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        if rhs_vec is not None:
            rhs_vec.destroy()
        if base_vec is not None:
            base_vec.destroy()
        if shifted_vec is not None:
            shifted_vec.destroy()
        if outer_bridge is not None:
            outer_bridge.destroy()
        if template is not None:
            template.destroy()
        if outer_mat is not None:
            outer_mat.destroy()
        if outer_context is not None:
            outer_context.destroy()
        if physical_action is not None:
            physical_action.destroy()
        if shifted_action is not None:
            shifted_action.destroy()
        if adjoint_action is not None:
            adjoint_action.destroy()
        if dtn_action is not None:
            dtn_action.destroy()
        del incident_form
        del physical_ufl, shifted_ufl, adjoint_ufl
        del epsilon0, abs_epsilon0, beta0, epsilon1, abs_epsilon1, beta1
        gc.collect()
    source_end = h2b._light_source()
    if error is None and not (
        _m6b_w2_source_identity_valid(source_end, expected_source_sha)
    ):
        error = "M6B W2 execution source changed during diagnostic"
    gate = (
        (
            _m6b_w7_s1_numeric_gate(
                screen_result.get("samples") if isinstance(screen_result, Mapping) else None
            )
            if screen and solver == "disk_fgmres_restart"
            else _m6b_w3_numeric_gate(
                screen_result.get("samples") if isinstance(screen_result, Mapping) else None
            )
            if screen
            else (_m6b_w2r_gate(measurements) if projected else _m6b_w2_gate(measurements))
        )
        if error is None
        else {
            "pass": False,
            "checks": {},
            "problems": ["worker_error"],
        }
    )
    if error is not None:
        status = "gate_failed"
    diagnostic_numeric_pass, screen_numeric_pass = _m6b_worker_numeric_pass_fields(
        screen=screen,
        error=error,
        gate=gate,
    )
    summary_payload = {
        "schema": screen_schema if screen else (M6B_W2R_SCHEMA if projected else M6B_W2_SCHEMA),
        "status": status if error is None else "gate_failed",
        "scope": (
            _m6b_w7_s1_scope()
            if screen and solver == "disk_fgmres_restart"
            else _m6b_w5_scope()
            if screen and solver == "disk_fgmres"
            else _m6b_w4_scope()
            if screen and solver == "fbcgs"
            else _m6b_w3_scope(phase=phase_name, shifted_beta=shifted_beta)
            if screen
            else (_m6b_w2r_scope() if projected else _m6b_w2_scope())
        ),
        "expected_source_sha": expected_source_sha,
        "source_at_start": source_start,
        "source_at_end": source_end,
        "runtime_identity": runtime,
        "p6": p6,
        "authority": authority,
        "jit_cache": {
            "source_inventory_sha256": M6B_W2_JIT_INVENTORY_SHA256,
            "source_before": source_cache_before,
            "source_after": source_cache_after,
            "source_final": source_cache_final,
            "before": cache_before,
            "after": cache_after,
            "final": cache_final,
            "unchanged": cache_before == cache_after == cache_final,
        },
        "measurements": measurements,
        "gate": gate,
        "factor_store_audit": store.audit_jsonable() if store is not None else None,
        "range_store_audit": range_carrier.audit if range_carrier is not None else None,
        "pc_audit": (
            w2_pc.audit
            if "w2_pc" in locals() and w2_pc is not None
            else None
        ),
        "predicted_live_set": (
            _m6b_w7_s1_predicted_live_set()
            if screen and solver == "disk_fgmres_restart"
            else _m6b_w5_predicted_live_set()
            if screen and solver == "disk_fgmres"
            else _m6b_w4_predicted_live_set()
            if screen and solver == "fbcgs"
            else _m6b_w3_predicted_live_set()
            if screen
            else (_m6b_w2r_predicted_live_set() if projected else {
            "base_bytes": M6B_W2_BASE_PREDICTED_LIVE_SET_BYTES,
            "external_residual_bytes": M6B_W2_EXTERNAL_RESIDUAL_BYTES,
            "composition_incremental_bytes": M6B_W2_COMPOSITION_INCREMENTAL_BYTES,
            "predicted_bytes": M6B_W2_PREDICTED_LIVE_SET_BYTES,
            "limit_bytes": M6B_W2_PREDICTED_LIVE_SET_LIMIT_BYTES,
            "gate": M6B_W2_PREDICTED_LIVE_SET_BYTES
            <= M6B_W2_PREDICTED_LIVE_SET_LIMIT_BYTES,
            "is_measurement": False,
            "derived_not_measured": True,
            "prediction_scope": "production_apply_not_diagnostic_measurement",
            "basis": "W1A predicted plus one frozen residual and W2 composition increment",
            })
        ),
        "architecture": {
            "fine_space": "uncondensed_fullspace",
            "global_matrix": False,
            "static_condensation": False,
            "trace_slab_pc": False,
            "pde_pass": False,
            "formal_pass": False,
        },
        "error": error,
        "formal_pass": False,
        "diagnostic_numeric_pass": diagnostic_numeric_pass,
        "pde_pass": False,
        "elapsed_wall_seconds": float(time.perf_counter() - started),
    }
    if screen:
        screen_fields = {
            "screen": screen_result,
            "screen_gate": gate,
            "w2r_negative_authority": w2r_negative_authority,
            "w2r_positive_authority": w2r_positive_authority,
            "screen_numeric_pass": screen_numeric_pass,
            "formal_pass": False,
            "architecture": {
                "fine_space": "uncondensed_fullspace",
                "global_matrix": False,
                "augmented_matrix": False,
                "static_condensation": False,
                "trace_slab_pc": False,
                "schur": False,
                "explicit_C_materialized_count": 0,
                "explicit_D_materialized_count": 0,
                "pde_pass": False,
                "formal_pass": False,
            },
        }
        if solver == "disk_fgmres_restart":
            screen_fields["w7_s1_pass"] = False
            screen_fields["architecture"]["dtn_matrix_free"] = True
        elif solver == "disk_fgmres":
            screen_fields["w5_pass"] = False
            screen_fields["architecture"]["dtn_matrix_free"] = True
        elif solver == "fbcgs":
            screen_fields["w4_pass"] = False
            screen_fields["architecture"]["dtn_matrix_free"] = True
        else:
            screen_fields["w3_pass"] = False
        summary_payload.update(screen_fields)
    elif projected:
        summary_payload.update(
            {
                "w2r_negative_authority": w2r_negative_authority,
                "w2r_pass": False,
            }
        )
    else:
        summary_payload["w2_pass"] = False
    summary = _attach_evidence(summary_payload)
    _write_json(summary_path, summary)
    return 0 if (
        summary["screen_numeric_pass"]
        if screen
        else summary["diagnostic_numeric_pass"]
    ) else 1


def _run_m6b_w2r_diagnostic(
    run_dir: Path,
    factor_authority_dir: Path,
    wave_authority_dir: Path,
    jit_cache_source: Path,
    expected_source_sha: str,
    w0_authority_file: Path,
) -> int:
    return _run_m6b_w2_diagnostic(
        run_dir,
        factor_authority_dir,
        wave_authority_dir,
        jit_cache_source,
        expected_source_sha,
        w0_authority_file,
        projected=True,
    )


def _run_m6b_w3_screen(
    run_dir: Path,
    factor_authority_dir: Path,
    wave_authority_dir: Path,
    jit_cache_source: Path,
    expected_source_sha: str,
    w0_authority_file: Path,
) -> int:
    """Run the fixed beta=1 time-harmonic screen with the W2R production PC."""

    return _run_m6b_w2_diagnostic(
        run_dir,
        factor_authority_dir,
        wave_authority_dir,
        jit_cache_source,
        expected_source_sha,
        w0_authority_file,
        projected=True,
        screen=True,
    )


def _run_m6b_w3_beta05_screen(
    run_dir: Path,
    factor_authority_dir: Path,
    wave_authority_dir: Path,
    jit_cache_source: Path,
    expected_source_sha: str,
    w0_authority_file: Path,
) -> int:
    """Run the fixed beta=0.5 time-harmonic screen with the W2R PC."""

    return _run_m6b_w2_diagnostic(
        run_dir,
        factor_authority_dir,
        wave_authority_dir,
        jit_cache_source,
        expected_source_sha,
        w0_authority_file,
        projected=True,
        screen=True,
        shifted_beta=M6B_W3_BETA05,
        factor_manifest_sha256=M6B_W3_BETA05_FACTOR_MANIFEST_SHA256,
        factor_source_sha=M6B_W3_BETA05_FACTOR_SOURCE_SHA,
    )


def _run_m6b_w4_fbcgs_screen(
    run_dir: Path,
    factor_authority_dir: Path,
    wave_authority_dir: Path,
    jit_cache_source: Path,
    expected_source_sha: str,
    w0_authority_file: Path,
) -> int:
    """Run the fixed beta=1 direct-solution FBCGS screen."""

    return _run_m6b_w2_diagnostic(
        run_dir,
        factor_authority_dir,
        wave_authority_dir,
        jit_cache_source,
        expected_source_sha,
        w0_authority_file,
        projected=True,
        screen=True,
        shifted_beta=M6B_W4_BETA,
        solver="fbcgs",
    )


def _run_m6b_w5_disk_fgmres_screen(
    run_dir: Path,
    factor_authority_dir: Path,
    wave_authority_dir: Path,
    jit_cache_source: Path,
    expected_source_sha: str,
    w0_authority_file: Path,
) -> int:
    """Run the fixed beta=1 disk-backed flexible-GMRES screen."""

    return _run_m6b_w2_diagnostic(
        run_dir,
        factor_authority_dir,
        wave_authority_dir,
        jit_cache_source,
        expected_source_sha,
        w0_authority_file,
        projected=True,
        screen=True,
        shifted_beta=M6B_W5_BETA,
        solver="disk_fgmres",
    )


def _run_m6b_w7_s1_screen(
    run_dir: Path,
    factor_authority_dir: Path,
    wave_authority_dir: Path,
    jit_cache_source: Path,
    expected_source_sha: str,
    w0_authority_file: Path,
    w5_compact_path: Path,
    w5_raw_dir: Path,
) -> int:
    """Run one fixed 200-step continuation cycle from frozen W5 iter200."""

    continuation = _m6b_w7_s1_load_w5_authority(w5_compact_path, w5_raw_dir)
    initial_solution = continuation.pop("initial_solution")
    try:
        return _run_m6b_w2_diagnostic(
            run_dir,
            factor_authority_dir,
            wave_authority_dir,
            jit_cache_source,
            expected_source_sha,
            w0_authority_file,
            projected=True,
            screen=True,
            shifted_beta=M6B_W5_BETA,
            solver="disk_fgmres_restart",
            initial_solution=initial_solution,
            continuation_authority=continuation,
        )
    finally:
        del initial_solution


def _m6b_command(command: str, run_dir: Path) -> list[str]:
    if command not in {"m6b-stage-worker", "m6b-builder", "m6b-worker"}:
        raise ValueError("M6B command identity is invalid")
    return [
        os.path.abspath(sys.executable),
        "-m",
        "benchmarks.run_task037_extra_m6b",
        command,
        "--run-dir",
        str(run_dir.resolve()),
    ]


def _m6b_phase_record(
    h2b: Any,
    run_dir: Path,
    monitor_phase: str,
    process_info: Mapping[str, Any],
    *,
    compiler_must_be_empty: bool,
    timeout_seconds: float,
) -> dict[str, Any]:
    drain = h2b._bounded_process_drain(process_info)
    record = dict(process_info)
    record["timeout_seconds"] = float(timeout_seconds)
    record["watchdog_rss_limit_bytes"] = M6B_WATCHDOG_RSS_LIMIT_BYTES
    record["completion_rss_limit_bytes"] = M6B_ONLINE_COMPLETION_RSS_LIMIT_BYTES
    record["processes_gone"] = bool(drain["gone"])
    record["drain"] = drain
    try:
        metrics = h2b._timeline_metrics(
            run_dir / f"{monitor_phase}_timeline.jsonl", monitor_phase
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        metrics = None
        record["timeline_error"] = f"{type(exc).__name__}: {exc}"
    record["timeline_metrics"] = metrics
    if isinstance(metrics, Mapping):
        record["peak_rss_bytes"] = int(metrics["peak_rss_bytes"])
        record["swap_bytes"] = int(metrics["swap_bytes"])
        record["compiler_descendant_pids"] = list(
            metrics["compiler_descendant_pids"]
        )
    elif compiler_must_be_empty:
        record["compiler_descendant_pids"] = None
    return record


def _m6b_phase_gate(
    h2b: Any,
    run_dir: Path,
    summary: Mapping[str, Any],
    process_record: Mapping[str, Any],
    *,
    monitor_phase: str,
    progress_phase: str,
    expected_events: Sequence[str],
    compiler_must_be_empty: bool,
    timeout_seconds: float,
    stage_cache: Any = None,
    stage_kernel: Any = None,
) -> bool:
    if monitor_phase not in {"stage", "builder", "online"}:
        return False
    if not isinstance(summary, Mapping) or not _evidence_valid(summary):
        return False
    expected_schema = {
        "stage": M6B_STAGE_SCHEMA,
        "builder": M6B_BUILDER_SCHEMA,
        "online": M6B_WORKER_SCHEMA,
    }[monitor_phase]
    expected_scope = {
        "stage": _m6b_scope(phase="stage"),
        "builder": _m6b_scope(phase="builder"),
        "online": _m6b_scope(phase="mpi1"),
    }[monitor_phase]
    if summary.get("schema") != expected_schema or summary.get("scope") != expected_scope:
        return False
    if not _m6b_lifecycle_valid(
        process_record,
        online=monitor_phase == "online",
        require_compiler_empty=compiler_must_be_empty,
    ):
        return False
    metrics = process_record.get("timeline_metrics")
    if not isinstance(metrics, Mapping):
        return False
    if (
        metrics.get("peak_rss_bytes") != process_record.get("peak_rss_bytes")
        or metrics.get("swap_bytes") != process_record.get("swap_bytes")
        or process_record.get("processes_gone") is not True
        or process_record.get("timeout_seconds") != timeout_seconds
    ):
        return False
    progress_path = {
        "stage": "m6b_stage_progress.jsonl",
        "builder": "m6b_builder_progress.jsonl",
        "online": "m6b_mpi1_progress.jsonl",
    }[monitor_phase]
    progress_phase_value = "mpi1" if monitor_phase == "online" else progress_phase
    if not _m6b_progress_valid(
        run_dir / progress_path, progress_phase_value, expected_events
    ):
        return False
    if summary.get("status") != "measurement_complete":
        return False
    runtime = summary.get("runtime_identity")
    if not h2b._runtime_valid(runtime) or not isinstance(runtime, Mapping):
        return False
    if not isinstance(runtime.get("compiler"), Mapping):
        return False
    if not h2b._source_pair_valid(
        summary.get("source_at_start"), summary.get("source_at_end")
    ):
        return False
    if not _m6b_expected_p6(summary.get("p6", {})):
        return False
    if monitor_phase == "stage":
        forms = summary.get("forms")
        return bool(
            isinstance(forms, Mapping)
            and isinstance(forms.get("cache_inventory"), list)
            and forms["cache_inventory"]
            == h2b._cache_snapshot(run_dir / "jit_cache")
            and _m6b_form_records_bound(
                forms.get("outer_volume"),
                forms.get("shifted_volume"),
                forms.get("shared_volume_kernel"),
                phase="stage",
            )
            and _m6b_material_tag_coverage_valid(
                forms.get("material_tag_coverage"), owned_cells=M6B_GLOBAL_CELLS
            )
        )
    if monitor_phase == "builder":
        cache = summary.get("cache")
        return bool(
            isinstance(cache, Mapping)
            and isinstance(stage_cache, list)
            and isinstance(stage_kernel, Mapping)
            and cache.get("before") == stage_cache == cache.get("after")
            and cache.get("unchanged") is True
            and _m6b_builder_factor_audit_valid(summary.get("factor_audit"))
            and _m6b_builder_summary_valid(summary)
            and summary.get("shared_volume_kernel") == stage_kernel
            and summary.get("factor_store") is not None
        )
    measurement = summary.get("measurement")
    if not isinstance(measurement, Mapping):
        return False
    cache = measurement.get("cache")
    return bool(
        isinstance(cache, Mapping)
        and isinstance(stage_cache, list)
        and isinstance(stage_kernel, Mapping)
        and cache.get("stage") == stage_cache
        and cache.get("before") == stage_cache
        and cache.get("after") == stage_cache
        and cache.get("final") == stage_cache
        and cache.get("unchanged") is True
        and isinstance(measurement.get("screen"), Mapping)
        and _m6b_screen_metadata_valid(measurement["screen"])
        and measurement.get("finite") is True
        and _m6b_loaded_factor_audit_valid(measurement.get("m6b_store_audit"))
        and _m6b_form_records_bound(
            measurement.get("form", {}).get("outer_volume")
            if isinstance(measurement.get("form"), Mapping)
            else None,
            measurement.get("form", {}).get("shifted_volume")
            if isinstance(measurement.get("form"), Mapping)
            else None,
            measurement.get("shared_volume_kernel"),
            phase="mpi1",
        )
        and _m6b_material_tag_coverage_valid(
            measurement.get("material_tag_coverage"), owned_cells=M6B_GLOBAL_CELLS
        )
        and all(
            measurement["shared_volume_kernel"][key] == stage_kernel[key]
            for key in (
                "operator_identity",
                "representation",
                "fixed_physics",
                "module_name",
                "ufl_signature",
                "ufcx_signature",
            )
        )
        and isinstance(measurement.get("rhs_binding"), Mapping)
        and isinstance(measurement["rhs_binding"].get("canonical"), Mapping)
    )


def _m6b_raw_artifacts(
    run_dir: Path, worker: Mapping[str, Any] | None
) -> dict[str, Any]:
    paths = {
        "m6b_stage_summary.json",
        "m6b_stage_progress.jsonl",
        "m6b_builder_summary.json",
        "m6b_builder_progress.jsonl",
        "m6b_mpi1_worker_summary.json",
        "m6b_mpi1_progress.jsonl",
        "stage_timeline.jsonl",
        "stage_stdout.txt",
        "stage_root_pid.json",
        "builder_timeline.jsonl",
        "builder_stdout.txt",
        "builder_root_pid.json",
        "online_timeline.jsonl",
        "online_stdout.txt",
        "online_root_pid.json",
        "shifted_lu_store/manifest.json",
    }
    store_manifest = run_dir / "shifted_lu_store" / "manifest.json"
    if store_manifest.is_file():
        try:
            manifest = _read_json(store_manifest)
            for relative in manifest.get("files", {}):
                paths.add(f"shifted_lu_store/{relative}")
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            pass
    if isinstance(worker, Mapping):
        measurement = worker.get("online_measurement")
        if isinstance(measurement, Mapping):
            rhs_binding = measurement.get("rhs_binding")
            rhs = (
                rhs_binding.get("canonical")
                if isinstance(rhs_binding, Mapping)
                else None
            )
            if isinstance(rhs, Mapping) and isinstance(rhs.get("path"), str):
                paths.add(rhs["path"])
                manifest_path = run_dir / rhs["path"]
                if manifest_path.is_file():
                    try:
                        manifest = _read_json(manifest_path)
                        for shard in manifest.get("per_rank_shards", []):
                            if isinstance(shard, Mapping) and isinstance(shard.get("filename"), str):
                                paths.add(shard["filename"])
                    except (OSError, TypeError, ValueError, json.JSONDecodeError):
                        pass
            screen = measurement.get("screen")
            if isinstance(screen, Mapping):
                samples = screen.get("samples")
                if isinstance(samples, Mapping):
                    for item in samples.values():
                        if isinstance(item, Mapping):
                            for artifact in item.get("artifacts", {}).values():
                                if isinstance(artifact, Mapping) and isinstance(artifact.get("path"), str):
                                    paths.add(artifact["path"])
    return {relative: _artifact(run_dir, relative) for relative in sorted(paths)}


def _run_m6b_watchdog(run_dir: Path) -> int:
    import time

    h2b = __import__("benchmarks.run_task037_extra_h2b", fromlist=["*"])
    run_dir = run_dir.resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    source_start = h2b._light_source()
    source_end = source_start
    predicted = _predicted_live_set()
    dynamic_predicted: dict[str, Any] | None = None
    commands = {
        "stage": _m6b_command("m6b-stage-worker", run_dir),
        "builder": _m6b_command("m6b-builder", run_dir),
        "online": _m6b_command("m6b-worker", run_dir),
    }
    phases: dict[str, Any] = {}
    phase_gates: dict[str, bool] = {}
    stage_summary: dict[str, Any] = {}
    builder_summary: dict[str, Any] = {}
    online_summary: dict[str, Any] = {}
    worker: dict[str, Any] | None = None
    phase_source_identity: dict[str, Any] = {
        "pass": False,
        "source_commit_full_sha": None,
        "phase_names": ["stage", "builder", "online", "watchdog"],
        "all_tracked_source_clean": False,
    }
    status = "controlled_stop"
    error: str | None = None
    try:
        if predicted["gate"] is not True:
            raise ValueError("M6B initial predicted live-set Gate failed")
        stage_process = h2b._monitor_phase(
            run_dir,
            "stage",
            commands["stage"],
            M6B_STAGE_TIMEOUT_SECONDS,
            M6B_WATCHDOG_RSS_LIMIT_BYTES,
        )
        phases["stage"] = _m6b_phase_record(
            h2b,
            run_dir,
            "stage",
            stage_process,
            compiler_must_be_empty=False,
            timeout_seconds=M6B_STAGE_TIMEOUT_SECONDS,
        )
        stage_path = run_dir / "m6b_stage_summary.json"
        if stage_path.is_file():
            stage_summary = _read_json(stage_path)
        phase_gates["stage"] = _m6b_phase_gate(
            h2b,
            run_dir,
            stage_summary,
            phases["stage"],
            monitor_phase="stage",
            progress_phase="stage",
            expected_events=M6B_STAGE_EVENTS,
            compiler_must_be_empty=False,
            timeout_seconds=M6B_STAGE_TIMEOUT_SECONDS,
        )
        if phase_gates["stage"]:
            builder_process = h2b._monitor_phase(
                run_dir,
                "builder",
                commands["builder"],
                M6B_BUILDER_TIMEOUT_SECONDS,
                M6B_WATCHDOG_RSS_LIMIT_BYTES,
            )
            phases["builder"] = _m6b_phase_record(
                h2b,
                run_dir,
                "builder",
                builder_process,
                compiler_must_be_empty=True,
                timeout_seconds=M6B_BUILDER_TIMEOUT_SECONDS,
            )
            builder_path = run_dir / "m6b_builder_summary.json"
            if builder_path.is_file():
                builder_summary = _read_json(builder_path)
            stage_cache = stage_summary.get("forms", {}).get("cache_inventory")
            phase_gates["builder"] = _m6b_phase_gate(
                h2b,
                run_dir,
                builder_summary,
                phases["builder"],
                monitor_phase="builder",
                progress_phase="builder",
                expected_events=M6B_BUILDER_EVENTS,
                compiler_must_be_empty=True,
                timeout_seconds=M6B_BUILDER_TIMEOUT_SECONDS,
                stage_cache=stage_cache,
                stage_kernel=stage_summary.get("forms", {}).get(
                    "shared_volume_kernel"
                ),
            )
        else:
            phase_gates["builder"] = False
            phases["builder"] = {"not_run_by_gate": True}
        if phase_gates["stage"] and phase_gates["builder"]:
            builder_factor_audit = builder_summary.get("factor_audit")
            if not isinstance(builder_factor_audit, Mapping):
                raise ValueError("M6B builder factor audit is missing")
            dynamic_predicted = _dynamic_predicted_live_set(
                builder_factor_audit["retained_total_bytes"]
            )
            if dynamic_predicted["gate"] is True:
                online_process = h2b._monitor_phase(
                    run_dir,
                    "online",
                    commands["online"],
                    M6B_ONLINE_TIMEOUT_SECONDS,
                    M6B_WATCHDOG_RSS_LIMIT_BYTES,
                )
                phases["online"] = _m6b_phase_record(
                    h2b,
                    run_dir,
                    "online",
                    online_process,
                    compiler_must_be_empty=True,
                    timeout_seconds=M6B_ONLINE_TIMEOUT_SECONDS,
                )
                online_path = run_dir / "m6b_mpi1_worker_summary.json"
                if online_path.is_file():
                    online_summary = _read_json(online_path)
                stage_cache = stage_summary.get("forms", {}).get("cache_inventory")
                phase_gates["online"] = _m6b_phase_gate(
                    h2b,
                    run_dir,
                    online_summary,
                    phases["online"],
                    monitor_phase="online",
                    progress_phase="mpi1",
                    expected_events=M6B_ONLINE_EVENTS,
                    compiler_must_be_empty=True,
                    timeout_seconds=M6B_ONLINE_TIMEOUT_SECONDS,
                    stage_cache=stage_cache,
                    stage_kernel=stage_summary.get("forms", {}).get(
                        "shared_volume_kernel"
                    ),
                )
            else:
                phase_gates["online"] = False
                phases["online"] = {
                    "not_run_by_gate": True,
                    "predicted_live_set": dynamic_predicted,
                }
        else:
            phase_gates["online"] = False
            phases["online"] = {"not_run_by_gate": True}
        source_end = h2b._light_source()
        phase_source_identity = _m6b_phase_source_identity(
            {
                "stage": stage_summary,
                "builder": builder_summary,
                "online": online_summary,
                "watchdog": {
                    "source_at_start": source_start,
                    "source_at_end": source_end,
                },
            }
        )
        if all(phase_gates.get(name) is True for name in ("stage", "builder", "online")) and phase_source_identity["pass"] is True:
            measurement = online_summary["measurement"]
            worker = _attach_evidence(
                {
                    "schema": M6B_WORKER_SCHEMA,
                    "status": "measurement_complete",
                    "scope": _m6b_scope(phase="mpi1"),
                    "p6": measurement["p6"],
                    "stage": phases["stage"],
                    "online": phases["online"],
                    "factor_store": measurement["m6b_store_audit"],
                    "builder_factor_audit": builder_summary["factor_audit"],
                    "screen": measurement["screen"]["samples"],
                    "screen_metadata": measurement["screen"],
                    "architecture": measurement["architecture"],
                    "runtime_identity": online_summary["runtime_identity"],
                    "source_at_start": online_summary["source_at_start"],
                    "source_at_end": online_summary["source_at_end"],
                    "phase_source_identity": phase_source_identity,
                    "cache": measurement["cache"],
                    "pc_repeat": measurement["pc_repeat"],
                    "rhs_binding": measurement["rhs_binding"],
                    "online_measurement": measurement,
                    "builder_summary": _artifact(run_dir, "m6b_builder_summary.json"),
                    "stage_summary": _artifact(run_dir, "m6b_stage_summary.json"),
                }
            )
            _write_json(run_dir / "m6b_worker_summary.json", worker)
            status = "measurement_complete"
        else:
            error = (
                "M6B phase/source Gate stopped before complete online measurement"
            )
    except (OSError, RuntimeError, TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        error = f"{type(exc).__name__}: {exc}"
    final_source_end = h2b._light_source()
    final_phase_source_identity = _m6b_phase_source_identity(
        {
            "stage": stage_summary,
            "builder": builder_summary,
            "online": online_summary,
            "watchdog": {
                "source_at_start": source_start,
                "source_at_end": final_source_end,
            },
        }
    )
    if final_phase_source_identity != phase_source_identity:
        if status == "measurement_complete":
            status = "controlled_stop"
            error = "M6B source identity changed before watchdog finalization"
        phase_source_identity = final_phase_source_identity
    source_end = final_source_end
    payload = _attach_evidence(
        {
            "schema": M6B_WATCHDOG_SCHEMA,
            "status": status,
            "pass": status == "measurement_complete",
            "scope": _m6b_scope(),
            "predicted_live_set": predicted,
            "dynamic_predicted_live_set": dynamic_predicted,
            "command_identity": commands,
            "phase_gates": phase_gates,
            "phase_source_identity": phase_source_identity,
            "phases": phases,
            "worker_summary": _artifact(run_dir, "m6b_worker_summary.json"),
            "raw_artifacts": _m6b_raw_artifacts(run_dir, worker),
            "source_at_start": source_start,
            "source_at_end": source_end,
            "error": error,
            "elapsed_wall_seconds": float(time.perf_counter() - started),
        }
    )
    _write_json(run_dir / "m6b_watchdog_summary.json", payload)
    return 0 if status == "measurement_complete" else 1


def _m6b_checkpoint_recompute(run_dir: Path, screen: Any) -> dict[str, Any]:
    import numpy as np

    required_iterations = {str(value) for value in M6B_SCREEN_ITERATIONS}
    problems: list[str] = []
    residuals: dict[str, float] = {}
    if not isinstance(screen, Mapping) or set(screen) != required_iterations:
        return {"pass": False, "problems": ["checkpoint_set"], "residuals": residuals}
    required_arrays = {"solution", "outer_action", "residual", "rhs"}
    for key in sorted(required_iterations, key=int):
        item = screen[key]
        if not isinstance(item, Mapping) or set(item.get("artifacts", {})) != required_arrays:
            problems.append(f"checkpoint_{key}_artifacts")
            continue
        arrays: dict[str, Any] = {}
        for name in sorted(required_arrays):
            record = item["artifacts"][name]
            expected_path = f"m6b_iter{int(key)}_{name}.npy"
            if (
                not isinstance(record, Mapping)
                or set(record) != {"path", "bytes", "sha256", "array_sha256", "shape", "dtype"}
                or record.get("path") != expected_path
            ):
                problems.append(f"checkpoint_{key}_{name}_identity")
                continue
            path = run_dir / expected_path
            actual = _artifact(run_dir, expected_path)
            if (
                actual.get("present") is not True
                or actual.get("bytes") != record.get("bytes")
                or actual.get("sha256") != record.get("sha256")
            ):
                problems.append(f"checkpoint_{key}_{name}_file")
                continue
            try:
                array = np.load(path, allow_pickle=False, mmap_mode="r")
                observed_array_sha = hashlib.sha256(
                    memoryview(np.ascontiguousarray(array)).cast("B")
                ).hexdigest()
                if (
                    array.dtype != np.dtype(np.complex128)
                    or list(array.shape) != [M6B_GLOBAL_ROWS]
                    or record.get("shape") != [M6B_GLOBAL_ROWS]
                    or record.get("dtype") != "complex128"
                    or observed_array_sha != record.get("array_sha256")
                    or not np.all(np.isfinite(array))
                ):
                    problems.append(f"checkpoint_{key}_{name}_array")
                arrays[name] = array
            except (OSError, TypeError, ValueError):
                problems.append(f"checkpoint_{key}_{name}_load")
        if set(arrays) != required_arrays:
            continue
        expected_residual = np.asarray(arrays["rhs"]) - np.asarray(arrays["outer_action"])
        closure = float(
            np.linalg.norm(expected_residual - np.asarray(arrays["residual"]))
            / max(float(np.linalg.norm(arrays["rhs"])), np.finfo(float).tiny)
        )
        relative = float(
            np.linalg.norm(expected_residual)
            / max(float(np.linalg.norm(arrays["rhs"])), np.finfo(float).tiny)
        )
        recorded = item.get("true_relative_residual")
        if (
            not _finite_number(recorded)
            or closure > 1.0e-12
            or abs(relative - float(recorded)) > 1.0e-12 * max(1.0, abs(relative))
        ):
            problems.append(f"checkpoint_{key}_residual")
        else:
            residuals[key] = relative
        del arrays, expected_residual
    return {"pass": not problems, "problems": problems, "residuals": residuals}


def _m6b_w5_numeric_gate(residuals: Any) -> dict[str, Any]:
    checks = {
        "true_residual_iter20": False,
        "true_residual_iter100": False,
        "true_residual_iter200": False,
        "improvement_150_to_200": False,
    }
    observed: dict[str, float] = {}
    if isinstance(residuals, Mapping):
        for key in ("20", "100", "150", "200"):
            if key in residuals and _finite_number(residuals[key]):
                value = float(residuals[key])
                if value >= 0.0:
                    observed[key] = value
    checks["true_residual_iter20"] = (
        "20" in observed and observed["20"] <= M6B_SCREEN_RHO_LIMITS["20"]
    )
    checks["true_residual_iter100"] = (
        "100" in observed and observed["100"] <= M6B_SCREEN_RHO_LIMITS["100"]
    )
    checks["true_residual_iter200"] = (
        "200" in observed and observed["200"] <= M6B_SCREEN_RHO_LIMITS["200"]
    )
    improvement = None
    if "150" in observed and "200" in observed and observed["150"] > 0.0:
        improvement = 1.0 - observed["200"] / observed["150"]
        checks["improvement_150_to_200"] = bool(
            math.isfinite(improvement) and improvement >= M6B_IMPROVEMENT_LIMIT
        )
    problems = [name for name, passed in checks.items() if not passed]
    result: dict[str, Any] = {
        "true_residuals": observed,
        "limits": {
            "iteration20": M6B_SCREEN_RHO_LIMITS["20"],
            "iteration100": M6B_SCREEN_RHO_LIMITS["100"],
            "iteration200": M6B_SCREEN_RHO_LIMITS["200"],
            "improvement_150_to_200": M6B_IMPROVEMENT_LIMIT,
        },
        "checks": checks,
        "problems": problems,
        "pass": not problems,
    }
    if improvement is not None and math.isfinite(improvement):
        result["improvement_150_to_200"] = float(improvement)
    return result


def _m6b_w5_progress_valid(path: Path, screen: Any) -> dict[str, Any]:
    fixed = (
        "authority_validated",
        "mesh_ready",
        "space_ready",
        "floquet_mpc_ready",
        "cache_ready",
        "outer_and_carriers_ready",
        "rhs_ready",
        "screen_started",
    )
    try:
        records = [json.loads(line) for line in path.read_text().splitlines()]
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return {"pass": False, "problems": [f"progress_read:{type(exc).__name__}"]}
    samples = screen.get("samples") if isinstance(screen, Mapping) else None
    if not isinstance(samples, Mapping):
        return {"pass": False, "problems": ["progress_screen"]}
    problems: list[str] = []
    position = 0
    for event in fixed:
        ok = (
            position < len(records)
            and isinstance(records[position], Mapping)
            and records[position].get("event") == event
        )
        if not ok:
            problems.append(f"progress_{event}")
        position += 1
    for count in range(10, 201, 10):
        record = records[position] if position < len(records) else None
        if not (
            isinstance(record, Mapping)
            and record.get("event") == "krylov_progress"
            and record.get("pc_apply_count") == count
            and record.get("completed_pc_applies") == count
            and record.get("max_pc_applies") == 200
        ):
            problems.append(f"progress_krylov_{count}")
        position += 1
        if count not in M6B_SCREEN_ITERATIONS:
            continue
        checkpoint = records[position] if position < len(records) else None
        sample = samples.get(str(count))
        sample_artifacts = sample.get("artifacts") if isinstance(sample, Mapping) else None
        progress_artifacts = (
            checkpoint.get("artifacts") if isinstance(checkpoint, Mapping) else None
        )
        artifact_ok = isinstance(sample_artifacts, Mapping) and isinstance(
            progress_artifacts, Mapping
        )
        if artifact_ok:
            for name in ("solution", "outer_action", "residual", "rhs"):
                left = progress_artifacts.get(name)
                right = sample_artifacts.get(name)
                artifact_ok = artifact_ok and isinstance(left, Mapping) and isinstance(
                    right, Mapping
                )
                if artifact_ok:
                    artifact_ok = all(
                        left.get(field) == right.get(field)
                        for field in ("path", "bytes", "sha256", "array_sha256")
                    )
        if not (
            isinstance(checkpoint, Mapping)
            and checkpoint.get("event") == "checkpoint_ready"
            and checkpoint.get("iteration") == count
            and _finite_number(checkpoint.get("true_relative_residual"))
            and artifact_ok
        ):
            problems.append(f"progress_checkpoint_{count}")
        position += 1
    for event in ("screen_ready", "summary_ready"):
        ok = (
            position < len(records)
            and isinstance(records[position], Mapping)
            and records[position].get("event") == event
        )
        if not ok:
            problems.append(f"progress_{event}")
        position += 1
    if position != len(records):
        problems.append("progress_event_count")
    return {
        "pass": not problems,
        "problems": problems,
        "record_count": len(records),
        "events": [
            record.get("event") if isinstance(record, Mapping) else None
            for record in records
        ],
    }


def _m6b_w5_timeline_valid(
    watchdog: Any,
    watchdog_dir: Path,
    *,
    timeline_name: str = "w5_disk_fgmres_screen_timeline.jsonl",
    expected_peak: int | None = M6B_W5_EXPECTED_PROCESS_PEAK_BYTES,
    artifact_key: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "pass": False,
        "records": 0,
        "peak_rss_bytes": None,
        "swap_bytes": None,
        "compiler_descendant_pids": None,
    }
    try:
        record = watchdog["artifacts"][
            timeline_name if artifact_key is None else artifact_key
        ]
        timeline_path = Path(record["path"])
        if not timeline_path.is_absolute():
            timeline_path = watchdog_dir / timeline_path
        records = [
            json.loads(line)
            for line in timeline_path.read_text().splitlines()
        ]
        rss = [record["rss_bytes"] for record in records]
        swaps = [record["swap_bytes"] for record in records]
        compiler = [record["compiler_descendant_pids"] for record in records]
        result.update(
            {
                "pass": bool(
                    records
                    and all(type(value) is int for value in rss)
                    and all(value == 0 for value in swaps)
                    and all(value == [] for value in compiler)
                    and (expected_peak is None or max(rss) == expected_peak)
                    and max(swaps) == 0
                ),
                "records": len(records),
                "peak_rss_bytes": max(rss) if rss else None,
                "swap_bytes": max(swaps) if swaps else None,
                "compiler_descendant_pids": sorted(
                    {pid for values in compiler for pid in values}
                ),
            }
        )
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        pass
    return result


def _m6b_w5_check_command(
    raw_dir: Path,
    watchdog_path: Path,
    output: Path,
    expected_producer_sha: str,
) -> int:
    try:
        checker_h2b = __import__(
            "benchmarks.run_task037_extra_h2b", fromlist=["_light_source"]
        )
        checker_source_start = checker_h2b._light_source()
        checker_source_error = None
    except (ImportError, OSError, RuntimeError, TypeError, ValueError) as exc:
        checker_h2b = None
        checker_source_start = None
        checker_source_error = f"{type(exc).__name__}: {exc}"

    try:
        worker = _read_json(raw_dir / "m6b_w5_summary.json")
        worker_read_error = None
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        worker = None
        worker_read_error = f"{type(exc).__name__}: {exc}"
    try:
        watchdog = _read_json(watchdog_path)
        watchdog_read_error = None
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        watchdog = None
        watchdog_read_error = f"{type(exc).__name__}: {exc}"

    def source_ok(value: Any) -> bool:
        return bool(
            isinstance(value, Mapping)
            and value.get("source_commit_full_sha") == expected_producer_sha
            and value.get("source_worktree_dirty") is False
            and value.get("tracked_source_dirty") is False
            and value.get("nonignored_untracked_paths") == []
            and value.get("worktree_status_porcelain") == []
            and value.get("git_error") is None
        )

    def file_ok(value: Any, base: Path) -> bool:
        if not isinstance(value, Mapping) or not {
            "path", "present", "bytes", "sha256"
        }.issubset(value):
            return False
        if (
            value["present"] is not True
            or type(value["bytes"]) is not int
            or value["bytes"] <= 0
            or not isinstance(value["path"], str)
            or not isinstance(value["sha256"], str)
            or len(value["sha256"]) != 64
        ):
            return False
        path = Path(value["path"])
        if not path.is_absolute():
            path = base / path
        try:
            return (
                path.is_file()
                and path.stat().st_size == value["bytes"]
                and _sha256_file(path) == value["sha256"]
            )
        except OSError:
            return False

    def inventory_ok(value: Any, base: Path) -> bool:
        if not isinstance(value, Mapping) or set(value) != {
            "raw", "watchdog", "preflight_v3", "wrapper"
        }:
            return False
        groups = {
            "raw": set(M6B_W5_RAW_ARTIFACT_NAMES),
            "watchdog": set(M6B_W5_WATCHDOG_ARTIFACT_NAMES),
            "preflight_v3": {"preflight"},
            "wrapper": {"wrapper"},
        }
        for group, names in groups.items():
            records = value.get(group)
            if not isinstance(records, Mapping) or set(records) != names:
                return False
            expected_dir = raw_dir if group == "raw" else watchdog_dir
            for name, record in records.items():
                if group in {"raw", "watchdog"}:
                    record_path = (
                        record.get("path") if isinstance(record, Mapping) else None
                    )
                    if not isinstance(record_path, str):
                        return False
                    path = Path(record_path)
                    if not path.is_absolute():
                        path = base / path
                    if path.resolve() != (expected_dir / name).resolve():
                        return False
                if not file_ok(record, base):
                    return False
        return True

    def runtime_ok(value: Any) -> bool:
        if not isinstance(value, Mapping):
            return False
        threads = value.get("threads")
        paths = value.get("package_paths")
        return bool(
            value.get("qualified_activation") == "1"
            and value.get("petsc_scalar_type") == "complex128"
            and value.get("petsc_int_type") == "int32"
            and value.get("mpi_size") == 1
            and value.get("linux_abi") is True
            and isinstance(value.get("sys_executable"), str)
            and ".venv" in value["sys_executable"]
            and isinstance(threads, Mapping)
            and all(threads.get(name) == "1" for name in (
                "OMP_NUM_THREADS",
                "OPENBLAS_NUM_THREADS",
                "MKL_NUM_THREADS",
                "NUMEXPR_NUM_THREADS",
            ))
            and isinstance(paths, Mapping)
            and all(
                isinstance(path, str) and "/mnt/c" not in path
                for path in paths.values()
            )
        )

    def authority_ok(value: Any) -> bool:
        if not isinstance(value, Mapping):
            return False
        factor = value.get("factor_manifest")
        wave = value.get("wave_manifest")
        w0 = value.get("w0_authority")
        artifact = w0.get("file_artifact") if isinstance(w0, Mapping) else None
        return bool(
            value.get("factor_beta") == 1.0
            and value.get("factor_source_sha") == M6B_W2_RESIDUAL_SOURCE_SHA
            and isinstance(factor, Mapping)
            and factor.get("sha256") == M6B_W2_FACTOR_MANIFEST_SHA256
            and isinstance(wave, Mapping)
            and wave.get("sha256") == M6B_W2_WAVE_MANIFEST_SHA256
            and value.get("wave_source_sha") == M6B_W2_WAVE_SOURCE_SHA
            and isinstance(w0, Mapping)
            and w0.get("schema") == "task037.m6b.wave_range_az_oracle.v1"
            and isinstance(artifact, Mapping)
            and artifact.get("sha256") == M6B_W2_W0_OUTPUT_SHA256
            and w0.get("basis_manifest_sha256") == M6B_W2_W0_BASIS_MANIFEST_SHA256
            and w0.get("az_column_sha256_aggregate")
            == M6B_W2_W0_AZ_COLUMN_SHA256_AGGREGATE
        )

    def architecture_ok(value: Any) -> bool:
        return bool(
            isinstance(value, Mapping)
            and set(value)
            == {
                "fine_space", "global_matrix", "augmented_matrix",
                "static_condensation", "trace_slab_pc", "dtn_matrix_free",
                "schur", "explicit_C_materialized_count",
                "explicit_D_materialized_count", "formal_pass", "pde_pass",
            }
            and value["fine_space"] == "uncondensed_fullspace"
            and value["global_matrix"] is False
            and value["augmented_matrix"] is False
            and value["static_condensation"] is False
            and value["trace_slab_pc"] is False
            and value["dtn_matrix_free"] is True
            and value["schur"] is False
            and value["explicit_C_materialized_count"] == 0
            and value["explicit_D_materialized_count"] == 0
            and value["formal_pass"] is False
            and value["pde_pass"] is False
        )

    worker_source_ok = bool(
        isinstance(worker, Mapping)
        and worker.get("expected_source_sha") == expected_producer_sha
        and source_ok(worker.get("source_at_start"))
        and source_ok(worker.get("source_at_end"))
    )
    screen = worker.get("screen") if isinstance(worker, Mapping) else None
    screen_ok = _m6b_w5_screen_metadata_valid(screen)
    recompute = _m6b_checkpoint_recompute(
        raw_dir, screen.get("samples") if isinstance(screen, Mapping) else None
    )
    numeric = _m6b_w5_numeric_gate(recompute.get("residuals"))
    checkpoint_artifacts: dict[str, Any] = {}
    samples = screen.get("samples") if isinstance(screen, Mapping) else None
    if isinstance(samples, Mapping):
        for key in (str(value) for value in M6B_SCREEN_ITERATIONS):
            item = samples.get(key)
            if not isinstance(item, Mapping) or not isinstance(
                item.get("artifacts"), Mapping
            ):
                continue
            checkpoint_artifacts[key] = {
                name: _artifact(raw_dir, record["path"])
                for name, record in item["artifacts"].items()
                if isinstance(record, Mapping) and isinstance(record.get("path"), str)
            }
    progress = _m6b_w5_progress_valid(
        raw_dir / "m6b_w5_progress.jsonl", screen
    )
    measurements = (
        worker.get("measurements") if isinstance(worker, Mapping) else None
    )
    measurement = (
        measurements.get("screen")
        if isinstance(measurements, Mapping)
        else None
    )
    form = measurement.get("form") if isinstance(measurement, Mapping) else None
    shared = (
        measurement.get("shared_volume_kernel")
        if isinstance(measurement, Mapping)
        else None
    )
    counts = (
        measurement.get("pc_audit", {}).get("production_action_counts")
        if isinstance(measurement, Mapping)
        and isinstance(measurement.get("pc_audit"), Mapping)
        else None
    )
    pc = measurement.get("pc_audit") if isinstance(measurement, Mapping) else None
    jit = worker.get("jit_cache") if isinstance(worker, Mapping) else None
    execution_checks: dict[str, bool] = {
        "input_read": worker_read_error is None and watchdog_read_error is None,
        "raw_evidence": isinstance(worker, Mapping) and _evidence_valid(worker),
        "worker_schema": isinstance(worker, Mapping)
        and worker.get("schema") == M6B_W5_SCHEMA,
        "worker_scope": isinstance(worker, Mapping)
        and worker.get("scope") == _m6b_w5_scope(),
        "worker_source": worker_source_ok,
        "screen_metadata": screen_ok,
        "runtime_identity": runtime_ok(
            worker.get("runtime_identity") if isinstance(worker, Mapping) else None
        ),
        "jit_identity": bool(
            isinstance(jit, Mapping)
            and jit.get("source_inventory_sha256") == M6B_W2_JIT_INVENTORY_SHA256
            and jit.get("unchanged") is True
            and all(
                isinstance(jit.get(name), Mapping)
                and jit[name].get("inventory_sha256") == M6B_W2_JIT_INVENTORY_SHA256
                for name in (
                    "before", "after", "final", "source_before", "source_final"
                )
            )
        ),
        "authority": authority_ok(
            worker.get("authority") if isinstance(worker, Mapping) else None
        ),
        "architecture": architecture_ok(
            worker.get("architecture") if isinstance(worker, Mapping) else None
        ),
        "form_binding": bool(
            isinstance(form, Mapping)
            and isinstance(shared, Mapping)
            and _m6b_shared_kernel_valid(
                shared, phase="mpi1", shifted_beta=1.0
            )
            and _m6b_form_records_bound(
                form.get("outer_volume"),
                form.get("shifted_volume"),
                shared,
                phase="mpi1",
                shifted_beta=1.0,
            )
        ),
        "pc_binding": bool(
            isinstance(pc, Mapping)
            and pc.get("schema")
            == "task037.extra.h2b.m6b.projected-range-pc.v1"
            and pc.get("local_beta") == 1.0
            and pc.get("fixed_order") == "projected_range_complement"
            and pc.get("scan") is False
            and counts
            == {"local_apply": 1, "physical_outer_action": 3, "range_apply": 2}
            and pc.get("fine_space") == "uncondensed_fullspace"
            and all(
                pc.get(name) is False
                for name in (
                    "global_matrix", "global_constraint_matrix", "patch_matrices",
                    "per_cell_factor", "static_condensation", "trace_slab_pc",
                    "schur", "slab_factor",
                )
            )
        ),
        "status_layering": bool(
            isinstance(worker, Mapping)
            and worker.get("status") == "gate_failed"
            and worker.get("error") is None
            and worker.get("diagnostic_numeric_pass") is False
            and worker.get("screen_numeric_pass") is False
            and worker.get("w5_pass") is False
            and worker.get("formal_pass") is False
            and worker.get("pde_pass") is False
        ),
        "watchdog_schema": isinstance(watchdog, Mapping)
        and watchdog.get("schema")
        == "task037.extra.m6b.w5.disk-fgmres.watchdog.v1",
        "watchdog_evidence": isinstance(watchdog, Mapping)
        and _evidence_valid(watchdog),
        "source_binding": bool(
            isinstance(watchdog, Mapping)
            and worker_source_ok
            and watchdog.get("source", {}).get("expected_sha")
            == expected_producer_sha
            and source_ok(watchdog.get("source", {}).get("start"))
            and source_ok(watchdog.get("source", {}).get("end"))
            and watchdog.get("source_end_clean") is True
        ),
        "progress": progress["pass"] is True,
        "checkpoint_recompute": recompute["pass"] is True,
        "checker_source": False,
    }
    if checker_h2b is not None and checker_source_start is not None:
        try:
            checker_source_end = checker_h2b._light_source()
            checker_source_error = None
            execution_checks["checker_source"] = bool(
                checker_h2b._source_pair_valid(
                    checker_source_start, checker_source_end
                )
            )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            checker_source_end = None
            checker_source_error = f"{type(exc).__name__}: {exc}"
    else:
        checker_source_end = None
    watchdog_dir = watchdog_path.parent
    inventory = (
        watchdog.get("artifact_inventory") if isinstance(watchdog, Mapping) else None
    )
    process = watchdog.get("process") if isinstance(watchdog, Mapping) else None
    drain = watchdog.get("drain") if isinstance(watchdog, Mapping) else None
    timeline = _m6b_w5_timeline_valid(
        watchdog, watchdog_dir
    ) if isinstance(watchdog, Mapping) else {
        "pass": False, "records": 0, "peak_rss_bytes": None,
        "swap_bytes": None, "compiler_descendant_pids": None,
    }
    resource_checks: dict[str, bool] = {
        "artifact_inventory": inventory_ok(inventory, watchdog_dir),
        "prediction": bool(
            isinstance(watchdog, Mapping)
            and watchdog.get("prediction") == _m6b_w5_predicted_live_set()
            and isinstance(worker, Mapping)
            and worker.get("predicted_live_set") == _m6b_w5_predicted_live_set()
            and isinstance(worker.get("predicted_live_set"), Mapping)
            and worker["predicted_live_set"].get("derived_not_measured") is True
            and worker["predicted_live_set"].get("is_measurement") is False
        ),
        "process": bool(
            isinstance(process, Mapping)
            and process.get("return_code") == 1
            and process.get("termination") is None
            and process.get("peak_rss_bytes") == M6B_W5_EXPECTED_PROCESS_PEAK_BYTES
            and process.get("swap_bytes") == 0
            and isinstance(drain, Mapping)
            and drain.get("gone") is True
            and isinstance(watchdog, Mapping)
            and watchdog.get("resource_limits") == {
                "timeout_seconds": 19200.0,
                "watchdog_rss_bytes": M6B_WATCHDOG_RSS_LIMIT_BYTES,
                "completion_peak_rss_bytes": M6B_ONLINE_COMPLETION_RSS_LIMIT_BYTES,
                "swap_bytes": 0,
                "pde_strict_peak_bytes": 2_000_000_000,
            }
        ),
        "timeline": bool(
            timeline["pass"] is True
            and isinstance(process, Mapping)
            and timeline["peak_rss_bytes"] == process.get("peak_rss_bytes")
            and timeline["swap_bytes"] == process.get("swap_bytes") == 0
            and timeline["compiler_descendant_pids"] == []
            and isinstance(watchdog, Mapping)
            and watchdog.get("timeline", {}).get("records") == timeline["records"]
        ),
        "watchdog_status": bool(
            isinstance(watchdog, Mapping)
            and watchdog.get("status") == "gate_failed"
            and watchdog.get("classification") == "NUMERIC_FAIL"
            and watchdog.get("w5_pass") is False
            and watchdog.get("formal_pass") is False
            and watchdog.get("pde_pass") is False
            and watchdog.get("official_rta") is False
            and watchdog.get("jit_unchanged") is True
            and watchdog.get("monitor_error") is None
        ),
    }
    execution_evidence_ok = all(execution_checks.values())
    resource_evidence_ok = all(resource_checks.values())
    numeric_ok = numeric["pass"] is True
    if not execution_evidence_ok:
        classification = "EXECUTION_FAIL"
    elif not resource_evidence_ok:
        classification = "RESOURCE_OR_EVIDENCE_FAIL"
    elif not numeric_ok:
        classification = "NUMERIC_FAIL"
    else:
        classification = "PASS"
    result: dict[str, Any] = {
        "schema": M6B_W5_CHECK_SCHEMA,
        "status": "pass" if classification == "PASS" else "gate_failed",
        "pass": classification == "PASS",
        "classification": classification,
        "execution_evidence_ok": execution_evidence_ok,
        "resource_evidence_ok": resource_evidence_ok,
        "numeric_ok": numeric_ok,
        "evidence_complete": execution_evidence_ok and resource_evidence_ok,
        "producer_source_sha": expected_producer_sha,
        "checker_source": {
            "start": checker_source_start,
            "end": checker_source_end,
            "error": checker_source_error,
        },
        "checks": {**execution_checks, **resource_checks},
        "problems": sorted(
            set(
                [
                    name
                    for name, passed in execution_checks.items()
                    if not passed
                ]
                + [
                    name
                    for name, passed in resource_checks.items()
                    if not passed
                ]
                + numeric["problems"]
                + [
                    error
                    for error in (worker_read_error, watchdog_read_error)
                    if error is not None
                ]
            )
        ),
        "numeric_gate": numeric,
        "checkpoint_recompute": recompute,
        "checkpoint_artifacts": checkpoint_artifacts,
        "progress": progress,
        "timeline": timeline,
        "prediction": None if watchdog is None else watchdog.get("prediction"),
        "process": process,
        "drain": drain,
        "raw_worker_artifact": _artifact(raw_dir, "m6b_w5_summary.json"),
        "raw_progress_artifact": _artifact(raw_dir, "m6b_w5_progress.jsonl"),
        "watchdog_artifact": _artifact(watchdog_dir, watchdog_path.name),
        "artifact_inventory": inventory,
        "screen": screen,
        "architecture": (
            worker.get("architecture") if isinstance(worker, Mapping) else None
        ),
        "jit_identity": jit,
        "authority": worker.get("authority") if isinstance(worker, Mapping) else None,
        "formal_pass": False,
        "w5_pass": False,
        "pde_pass": False,
        "official_rta": False,
    }
    _write_json(output, _attach_evidence(result))
    return 0 if result["pass"] else 1


def _m6b_w6a_check_command(
    raw_dir: Path,
    legacy_store_dir: Path,
    output: Path,
    expected_source_sha: str,
) -> int:
    checks = {
        "summary": False,
        "source": False,
        "scope": False,
        "prediction": False,
        "progress": False,
        "store": False,
        "residual_artifacts": False,
    }
    problems: list[str] = []
    summary: dict[str, Any] | None = None
    try:
        summary = _read_json(raw_dir / "w6a_summary.json")
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        problems.append(f"summary_read:{type(exc).__name__}")
    if isinstance(summary, Mapping):
        checks["summary"] = bool(
            summary.get("schema") == M6B_W6A_SCHEMA
            and _evidence_valid(summary)
            and summary.get("status") in {"diagnostic_complete", "gate_failed"}
            and summary.get("formal_pass") is False
            and summary.get("pde_pass") is False
        )
        source_start = summary.get("source_at_start")
        source_end = summary.get("source_at_end")
        checks["source"] = bool(
            isinstance(source_start, Mapping)
            and isinstance(source_end, Mapping)
            and source_start.get("source_commit_full_sha") == expected_source_sha
            and source_end.get("source_commit_full_sha") == expected_source_sha
            and source_start.get("tracked_source_dirty") is False
            and source_end.get("tracked_source_dirty") is False
            and source_start.get("worktree_status_porcelain") == []
            and source_end.get("worktree_status_porcelain") == []
        )
        prediction = summary.get("prediction")
        if isinstance(prediction, Mapping):
            prediction_keys = (
                "old_retained_bytes",
                "new_retained_bytes",
                "old_work_bytes",
                "new_work_bytes",
            )
            if all(type(prediction.get(key)) is int for key in prediction_keys):
                try:
                    recomputed = _m6b_w6a_predicted_live_set(
                        old_retained_bytes=prediction["old_retained_bytes"],
                        new_retained_bytes=prediction["new_retained_bytes"],
                        old_work_bytes=prediction["old_work_bytes"],
                        new_work_bytes=prediction["new_work_bytes"],
                    )
                    checks["prediction"] = prediction == recomputed
                    checks["scope"] = summary.get("scope") == _m6b_w6a_scope(
                        prediction=recomputed
                    )
                except (TypeError, ValueError):
                    checks["prediction"] = False
                    checks["scope"] = False
        progress_record = summary.get("progress_artifact")
        if isinstance(progress_record, Mapping) and progress_record.get("path") == "w6a_progress.jsonl":
            actual = _artifact(raw_dir, "w6a_progress.jsonl")
            checks["progress"] = bool(
                actual == progress_record
                and _m6b_w6a_progress_valid(raw_dir / "w6a_progress.jsonl").get("pass") is True
            )
        manifest_record = summary.get("store_manifest_artifact")
        if isinstance(manifest_record, Mapping) and manifest_record.get("path") == "sparse_range_store/manifest.json":
            actual = _artifact(raw_dir, "sparse_range_store/manifest.json")
            if actual == manifest_record:
                from src.solvers.hcurl_m6b_w6a_multi_order_range import validate_w6a_store

                checks["store"] = validate_w6a_store(
                    raw_dir / "sparse_range_store/manifest.json",
                    legacy_store_dir=legacy_store_dir,
                ).get("pass") is True
        residual_artifacts = summary.get("residual_artifacts")
        if isinstance(residual_artifacts, Mapping) and set(residual_artifacts) == {
            "20", "100", "150", "200"
        }:
            import numpy as np

            valid_artifacts = True
            for iteration, record in residual_artifacts.items():
                expected_name = f"m6b_w6a_residual_iter{int(iteration)}.npy"
                path = raw_dir / expected_name
                if (
                    not isinstance(record, Mapping)
                    or record.get("path") != expected_name
                    or _artifact(raw_dir, expected_name).get("present") is not True
                    or _artifact(raw_dir, expected_name).get("sha256") != record.get("sha256")
                ):
                    valid_artifacts = False
                    continue
                try:
                    array = np.load(path, allow_pickle=False, mmap_mode="r")
                    valid_artifacts = valid_artifacts and bool(
                        array.dtype == np.dtype(np.complex128)
                        and list(array.shape) == [M6B_GLOBAL_ROWS]
                        and np.all(np.isfinite(array))
                        and _m6b_w2_array_sha256(array) == record.get("array_sha256")
                    )
                except (OSError, TypeError, ValueError):
                    valid_artifacts = False
            checks["residual_artifacts"] = valid_artifacts
    execution_ok = all(checks.values())
    numeric: dict[str, Any] = {
        "checks": {},
        "observed": {},
        "problems": ["execution_evidence_incomplete"],
        "pass": False,
    }
    if execution_ok:
        try:
            from src.solvers.hcurl_m6b_w6a_multi_order_range import (
                W6AMultiOrderRangeDiagnostic,
            )

            store = W6AMultiOrderRangeDiagnostic.load(
                raw_dir / "sparse_range_store/manifest.json",
                legacy_store_dir=legacy_store_dir,
            )
            try:
                import numpy as np

                residuals: dict[str, dict[str, float]] = {}
                for iteration in ("20", "100", "150", "200"):
                    array = np.load(
                        raw_dir / f"m6b_w6a_residual_iter{int(iteration)}.npy",
                        allow_pickle=False,
                        mmap_mode="r",
                    )
                    result = store.compare_range_orders(array)
                    residuals[iteration] = {
                        "rho75": float(result["rho75"]),
                        "rho390": float(result["rho390"]),
                    }
                numeric = _m6b_w6a_numeric_gate(residuals)
            finally:
                store.close()
        except (ImportError, OSError, TypeError, ValueError, KeyError) as exc:
            numeric = {
                "checks": {},
                "observed": {},
                "problems": [f"range_recompute:{type(exc).__name__}"],
                "pass": False,
            }
    else:
        problems.extend(key for key, passed in checks.items() if not passed)
    classification = (
        "PRE_FORMAL_PASS"
        if execution_ok and numeric["pass"]
        else "NUMERIC_FAIL"
        if execution_ok
        else "EXECUTION_FAIL"
    )
    result = {
        "schema": "task037.extra.m6b.w6a.multi-order-range.check.v1",
        "status": "diagnostic_complete" if execution_ok else "execution_failed",
        "classification": classification,
        "execution_evidence_ok": execution_ok,
        "formal_qualification": "not_run",
        "checks": checks,
        "numeric": numeric,
        "problems": sorted(set(problems + list(numeric.get("problems", [])))),
        "producer_source_sha": expected_source_sha,
        "checker_source_sha": None,
        "formal_pass": False,
        "pde_pass": False,
    }
    _write_json(output, _attach_evidence(result))
    return 0 if classification == "PRE_FORMAL_PASS" else 1


def _m6b_w7_s1_progress_valid(path: Path, screen: Any) -> dict[str, Any]:
    base = _m6b_w5_progress_valid(path, screen)
    if base.get("pass") is not True:
        return base
    try:
        records = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
        ]
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return {"pass": False, "problems": [f"progress_read:{type(exc).__name__}"]}
    samples = screen.get("samples") if isinstance(screen, Mapping) else None
    observed = []
    for record in records:
        if not isinstance(record, Mapping) or record.get("event") != "checkpoint_ready":
            continue
        iteration = record.get("iteration")
        if "cumulative_iteration" in record:
            cumulative = record["cumulative_iteration"]
        else:
            sample = (
                samples.get(str(iteration))
                if isinstance(samples, Mapping)
                else None
            )
            cumulative = (
                sample.get("cumulative_iteration")
                if isinstance(sample, Mapping)
                else None
            )
        observed.append((iteration, cumulative))
    expected = list(
        zip(M6B_W7_S1_LOCAL_ITERATIONS, M6B_W7_S1_CUMULATIVE_ITERATIONS)
    )
    return {
        **base,
        "pass": observed == expected,
        "problems": list(base.get("problems", []))
        + ([] if observed == expected else ["progress_checkpoint_mapping"]),
    }


def _m6b_w7_s1_artifact_inventory_valid(
    inventory: Any, raw_dir: Path, watchdog_dir: Path
) -> bool:
    if not isinstance(inventory, Mapping):
        return False
    raw_inventory = inventory.get("raw")
    watchdog_inventory = inventory.get("watchdog")
    if not isinstance(raw_inventory, Mapping) or not isinstance(
        watchdog_inventory, Mapping
    ):
        return False
    for name in M6B_W7_S1_RAW_ARTIFACT_NAMES:
        actual = _artifact(raw_dir, name)
        if actual.get("present") is not True or raw_inventory.get(name) != actual:
            return False
    for name in M6B_W7_S1_WATCHDOG_ARTIFACT_NAMES:
        actual = _artifact(watchdog_dir, name)
        if (
            actual.get("present") is not True
            or watchdog_inventory.get(name) != actual
        ):
            return False
    return True


def _m6b_w7_s1_check_command(
    raw_dir: Path,
    watchdog_path: Path,
    w5_compact_path: Path,
    w5_raw_dir: Path,
    jit_cache_source: Path,
    output: Path,
    expected_source_sha: str,
) -> int:
    checker_h2b = None
    checker_source_start: Mapping[str, Any] | None = None
    checker_source_end: Mapping[str, Any] | None = None
    raw_dir = Path(raw_dir).resolve()
    watchdog_path = Path(watchdog_path).resolve()
    watchdog_dir = watchdog_path.parent
    try:
        checker_h2b = __import__(
            "benchmarks.run_task037_extra_h2b", fromlist=["_light_source"]
        )
        checker_source_start = checker_h2b._light_source()
    except (ImportError, OSError, RuntimeError, TypeError, ValueError):
        checker_source_start = None
    problems: list[str] = []
    try:
        worker = _read_json(raw_dir / "m6b_w7_s1_summary.json")
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        worker = None
        problems.append("worker_summary")
    try:
        watchdog = _read_json(watchdog_path)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        watchdog = None
        problems.append("watchdog_summary")
    try:
        continuation = _m6b_w7_s1_load_w5_authority(
            w5_compact_path, w5_raw_dir
        )
        del (
            continuation["initial_solution"],
            continuation["frozen_rhs"],
            continuation["frozen_outer_action"],
            continuation["frozen_residual"],
        )
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        continuation = None
        problems.append(f"w5_authority:{type(exc).__name__}")

    screen = worker.get("screen") if isinstance(worker, Mapping) else None
    screen_samples = (
        screen.get("samples") if isinstance(screen, Mapping) else None
    )
    continuation_record = (
        screen.get("continuation_authority")
        if isinstance(screen, Mapping)
        else None
    )
    initial_check = (
        continuation_record.get("initial_check")
        if isinstance(continuation_record, Mapping)
        else None
    )
    watchdog_start = (
        watchdog.get("source_at_start") if isinstance(watchdog, Mapping) else None
    )
    watchdog_end = (
        watchdog.get("source_at_end") if isinstance(watchdog, Mapping) else None
    )
    execution_checks = {
        "worker_evidence": bool(
            isinstance(worker, Mapping)
            and _evidence_valid(worker)
            and worker.get("schema") == M6B_W7_S1_SCHEMA
        ),
        "source": bool(
            isinstance(worker, Mapping)
            and _m6b_w2_source_identity_valid(
                worker.get("source_at_start"), expected_source_sha
            )
            and _m6b_w2_source_identity_valid(
                worker.get("source_at_end"), expected_source_sha
            )
        ),
        "scope": isinstance(worker, Mapping)
        and worker.get("scope") == _m6b_w7_s1_scope(),
        "screen_metadata": _m6b_w7_s1_screen_metadata_valid(screen),
        "prediction": isinstance(worker, Mapping)
        and worker.get("predicted_live_set")
        == _m6b_w7_s1_predicted_live_set(),
        "status_layering": bool(
            isinstance(worker, Mapping)
            and worker.get("diagnostic_numeric_pass") is False
            and worker.get("w7_s1_pass") is False
            and worker.get("formal_pass") is False
            and worker.get("pde_pass") is False
        ),
        "architecture": bool(
            isinstance(worker, Mapping)
            and isinstance(worker.get("architecture"), Mapping)
            and worker["architecture"].get("fine_space")
            == "uncondensed_fullspace"
            and worker["architecture"].get("dtn_matrix_free") is True
            and all(
                worker["architecture"].get(name) is False
                for name in (
                    "global_matrix",
                    "augmented_matrix",
                    "static_condensation",
                    "trace_slab_pc",
                    "schur",
                )
            )
        ),
        "continuation": bool(
            continuation is not None
            and isinstance(continuation_record, Mapping)
            and continuation_record.get("compact")
            == continuation["compact"]
            and continuation_record.get("frozen_iteration") == 200
            and isinstance(initial_check, Mapping)
            and initial_check.get("initial_solution_provided") is True
            and initial_check.get("precheck_action_count") == 2
            and initial_check.get("core_initial_action_count") == 1
            and initial_check.get("rhs_equal_to_frozen_w5") is True
            and _finite_number(initial_check.get("repeat_relative_error"))
            and initial_check.get("repeat_relative_error") <= 1.0e-15
            and _finite_number(initial_check.get("frozen_action_relative_error"))
            and initial_check.get("frozen_action_relative_error") <= 1.0e-12
            and _finite_number(initial_check.get("frozen_residual_relative_error"))
            and initial_check.get("frozen_residual_relative_error") <= 1.0e-12
            and _finite_number(initial_check.get("rho_absolute_error"))
            and initial_check.get("rho_absolute_error") <= 1.0e-12
        ),
    }
    recompute = _m6b_checkpoint_recompute(raw_dir, screen_samples)
    numeric = _m6b_w7_s1_numeric_gate(
        screen_samples,
        recomputed_residuals=recompute.get("residuals")
        if isinstance(recompute, Mapping) and recompute.get("pass") is True
        else None,
    )
    execution_checks["checkpoint_recompute"] = recompute.get("pass") is True
    execution_checks["progress"] = _m6b_w7_s1_progress_valid(
        raw_dir / "m6b_w7_s1_progress.jsonl", screen
    ).get("pass") is True
    jit = worker.get("jit_cache") if isinstance(worker, Mapping) else None
    jit_identity_ok = False
    if checker_h2b is not None and isinstance(jit, Mapping):
        try:
            source_now = _m6b_w2_cache_record(
                checker_h2b, Path(jit_cache_source).resolve()
            )
            target_now = _m6b_w2_cache_record(
                checker_h2b, raw_dir / "jit_cache"
            )
            jit_identity_ok = bool(
                jit.get("source_inventory_sha256") == M6B_W2_JIT_INVENTORY_SHA256
                and jit.get("source_before")
                == jit.get("source_after")
                == jit.get("source_final")
                == source_now
                and jit.get("before")
                == jit.get("after")
                == jit.get("final")
                == target_now
                and jit.get("unchanged") is True
                and source_now == target_now
            )
        except (OSError, TypeError, ValueError, KeyError):
            jit_identity_ok = False
    execution_checks["jit_identity"] = jit_identity_ok
    if checker_h2b is not None and checker_source_start is not None:
        try:
            checker_source_end = checker_h2b._light_source()
        except (OSError, RuntimeError, TypeError, ValueError):
            checker_source_end = None
    checker_source_sha = (
        checker_source_start.get("source_commit_full_sha")
        if isinstance(checker_source_start, Mapping)
        else None
    )
    execution_checks["checker_source"] = bool(
        isinstance(checker_source_sha, str)
        and _m6b_w2_source_identity_valid(
            checker_source_start, checker_source_sha
        )
        and _m6b_w2_source_identity_valid(checker_source_end, checker_source_sha)
    )
    execution_evidence_ok = all(execution_checks.values())

    process = watchdog.get("process") if isinstance(watchdog, Mapping) else None
    drain = watchdog.get("drain") if isinstance(watchdog, Mapping) else None
    timeline = _m6b_w5_timeline_valid(
        watchdog,
        watchdog_dir,
        timeline_name="w7_s1_restart_disk_fgmres_screen_timeline.jsonl",
        expected_peak=None,
        artifact_key="timeline",
    )
    reported_artifacts = (
        watchdog.get("artifacts") if isinstance(watchdog, Mapping) else None
    )
    artifact_inventory = None
    artifact_inventory_ok = False
    if isinstance(reported_artifacts, Mapping):
        raw_artifact_labels = {
            "m6b_w7_s1_summary.json": "worker_summary",
            "m6b_w7_s1_progress.jsonl": "progress",
        }
        raw_inventory = {
            name: _artifact(raw_dir, name)
            for name in M6B_W7_S1_RAW_ARTIFACT_NAMES
        }
        watchdog_artifact_labels = {
            "w7_s1_restart_disk_fgmres_screen_root_pid.json": "root_pid",
            "w7_s1_restart_disk_fgmres_screen_stdout.txt": "stdout",
            "w7_s1_restart_disk_fgmres_screen_timeline.jsonl": "timeline",
        }
        watchdog_inventory = {
            name: _artifact(watchdog_dir, name)
            for name, label in watchdog_artifact_labels.items()
        }
        artifact_inventory = {
            "raw": raw_inventory,
            "watchdog": watchdog_inventory,
        }
        reported_raw_ok = True
        for name, label in raw_artifact_labels.items():
            actual = raw_inventory[name]
            reported = reported_artifacts.get(label)
            reported_raw_ok = reported_raw_ok and bool(
                isinstance(reported, Mapping)
                and reported.get("present") is True
                and isinstance(reported.get("path"), str)
                and Path(reported["path"]).resolve() == (raw_dir / name).resolve()
                and reported.get("bytes") == actual.get("bytes")
                and reported.get("sha256") == actual.get("sha256")
            )
        reported_watchdog_ok = True
        for name, label in watchdog_artifact_labels.items():
            actual = _artifact(watchdog_dir, name)
            reported = reported_artifacts.get(label)
            reported_watchdog_ok = reported_watchdog_ok and bool(
                isinstance(reported, Mapping)
                and reported.get("present") is True
                and isinstance(reported.get("path"), str)
                and Path(reported["path"]).resolve()
                == (watchdog_dir / name).resolve()
                and reported.get("bytes") == actual.get("bytes")
                and reported.get("sha256") == actual.get("sha256")
            )
        artifact_inventory_ok = bool(
            reported_raw_ok
            and reported_watchdog_ok
            and _m6b_w7_s1_artifact_inventory_valid(
                artifact_inventory, raw_dir, watchdog_dir
            )
        )
    resource_checks = {
        "artifact_inventory": artifact_inventory_ok,
        "process": bool(
            isinstance(process, Mapping)
            and process.get("return_code") in (0, 1)
            and process.get("termination") is None
            and type(process.get("peak_rss_bytes")) is int
            and process["peak_rss_bytes"] < M6B_ONLINE_COMPLETION_RSS_LIMIT_BYTES
            and process.get("swap_bytes") == 0
            and isinstance(drain, Mapping)
            and drain.get("gone") is True
        ),
        "timeline": bool(
            timeline["pass"] is True
            and isinstance(process, Mapping)
            and timeline["peak_rss_bytes"] == process.get("peak_rss_bytes")
            and timeline["swap_bytes"] == process.get("swap_bytes") == 0
            and timeline["compiler_descendant_pids"] == []
        ),
        "watchdog": bool(
            isinstance(watchdog, Mapping)
            and _evidence_valid(watchdog)
            and watchdog.get("schema")
            == "task037.extra.m6b.w7-s1.watchdog.v1"
            and watchdog.get("phase") == M6B_W7_S1_PHASE
            and isinstance(watchdog_start, Mapping)
            and _m6b_w2_source_identity_valid(
                watchdog_start, expected_source_sha
            )
            and isinstance(watchdog_end, Mapping)
            and _m6b_w2_source_identity_valid(watchdog_end, expected_source_sha)
            and watchdog.get("termination") is None
            and watchdog.get("monitor_error") is None
            and watchdog.get("resource_limits") == {
                "timeout_seconds": M6B_W7_S1_TIMEOUT_SECONDS,
                "watchdog_rss_bytes": M6B_WATCHDOG_RSS_LIMIT_BYTES,
                "completion_peak_rss_bytes": M6B_ONLINE_COMPLETION_RSS_LIMIT_BYTES,
                "swap_bytes": 0,
                "pde_strict_peak_bytes": 2_000_000_000,
            }
            and watchdog.get("formal_pass") is False
            and watchdog.get("pde_pass") is False
        ),
    }
    resource_evidence_ok = all(resource_checks.values())
    numeric_ok = numeric["pass"] is True
    if not execution_evidence_ok:
        classification = "EXECUTION_FAIL"
    elif not resource_evidence_ok:
        classification = "RESOURCE_OR_EVIDENCE_FAIL"
    elif not numeric_ok:
        classification = "NUMERIC_FAIL"
    else:
        classification = "PASS"
    result = {
        "schema": M6B_W7_S1_CHECK_SCHEMA,
        "status": "pass" if classification == "PASS" else "gate_failed",
        "pass": classification == "PASS",
        "classification": classification,
        "execution_evidence_ok": execution_evidence_ok,
        "resource_evidence_ok": resource_evidence_ok,
        "numeric_ok": numeric_ok,
        "checks": {**execution_checks, **resource_checks},
        "problems": sorted(
            set(
                problems
                + [name for name, passed in execution_checks.items() if not passed]
                + [name for name, passed in resource_checks.items() if not passed]
                + numeric["problems"]
            )
        ),
        "numeric_gate": numeric,
        "checkpoint_recompute": recompute,
        "process": process,
        "drain": drain,
        "timeline": timeline,
        "prediction": worker.get("predicted_live_set")
        if isinstance(worker, Mapping)
        else None,
        "producer_source_sha": expected_source_sha,
        "checker_source": {
            "start": checker_source_start,
            "end": checker_source_end,
        },
        "raw_worker_artifact": _artifact(raw_dir, "m6b_w7_s1_summary.json"),
        "raw_progress_artifact": _artifact(raw_dir, "m6b_w7_s1_progress.jsonl"),
        "watchdog_artifact": _artifact(watchdog_dir, watchdog_path.name),
        "artifact_inventory": artifact_inventory,
        "formal_pass": False,
        "w7_s1_pass": classification == "PASS",
        "pde_pass": False,
        "official_rta": False,
    }
    _write_json(output, _attach_evidence(result))
    return 0 if result["pass"] else 1


def _m6b_w6a_w5_residual_files_valid(
    residual_artifacts: Any,
    raw_dir: Path,
    w5_raw_dir: Path,
    *,
    compact_record: Mapping[str, Any] | None = None,
) -> bool:
    """Bind copied W5 residuals to both their source files and tracked compact evidence."""

    import numpy as np

    try:
        compact = (
            compact_record
            if compact_record is not None
            else _m6b_w6a_w5_compact_authority()["record"]
        )
        compact_samples = compact["screen"]["samples"]
        if not (
            _evidence_valid(compact)
            and compact.get("classification") == "NUMERIC_FAIL"
            and compact.get("producer_source_sha") == M6B_W6A_W5_SOURCE_SHA
            and isinstance(compact_samples, Mapping)
        ):
            return False
        if not isinstance(residual_artifacts, Mapping) or set(residual_artifacts) != {
            str(iteration) for iteration in M6B_W6A_W5_RESIDUAL_ITERATIONS
        }:
            return False
        for iteration in M6B_W6A_W5_RESIDUAL_ITERATIONS:
            record = residual_artifacts[str(iteration)]
            source_name = f"m6b_iter{iteration}_residual.npy"
            copy_name = f"m6b_w6a_residual_iter{iteration}.npy"
            source_artifact = _artifact(w5_raw_dir, source_name)
            copy_artifact = _artifact(raw_dir, copy_name)
            authority = compact_samples[str(iteration)]["artifacts"]["residual"]
            source_values = np.load(
                w5_raw_dir / source_name, allow_pickle=False, mmap_mode="r"
            )
            copy_values = np.load(
                raw_dir / copy_name, allow_pickle=False, mmap_mode="r"
            )
            authority_array_sha256 = _m6b_w6a_w5_legacy_raw_array_sha256(
                source_values
            )
            source_array_sha256 = _m6b_w2_array_sha256(source_values)
            copy_array_sha256 = _m6b_w2_array_sha256(copy_values)
            authority_ok = bool(
                isinstance(authority, Mapping)
                and authority.get("path") == source_name
                and authority.get("bytes") == source_artifact.get("bytes")
                and authority.get("sha256") == source_artifact.get("sha256")
                and authority.get("array_sha256") == authority_array_sha256
                and authority.get("dtype") == "complex128"
                and authority.get("shape") == [M6B_GLOBAL_ROWS]
            )
            if not (
                isinstance(record, Mapping)
                and record.get("path") == copy_name
                and record.get("source") == source_artifact
                and record.get("copy") == copy_artifact
                and source_artifact.get("present") is True
                and copy_artifact.get("present") is True
                and source_values.dtype == np.dtype(np.complex128)
                and copy_values.dtype == np.dtype(np.complex128)
                and list(source_values.shape) == [M6B_GLOBAL_ROWS]
                and list(copy_values.shape) == [M6B_GLOBAL_ROWS]
                and np.all(np.isfinite(source_values))
                and np.all(np.isfinite(copy_values))
                and source_array_sha256 == record.get("source_array_sha256")
                and copy_array_sha256 == record.get("copy_array_sha256")
                and source_array_sha256 == record.get("copy_array_sha256")
                and np.array_equal(source_values, copy_values)
                and authority_ok
            ):
                return False
        return True
    except (OSError, TypeError, ValueError, KeyError, IndexError, json.JSONDecodeError):
        return False


def _m6b_w6a_formal_check_command(
    raw_dir: Path,
    watchdog_summary_path: Path,
    legacy_store_dir: Path,
    w5_raw_dir: Path,
    jit_cache_source: Path,
    output: Path,
    expected_source_sha: str,
) -> int:
    """Independently adjudicate one completed W6A producer/watchdog pair."""

    import numpy as np

    h2b = __import__("benchmarks.run_task037_extra_h2b", fromlist=["*"])
    from src.solvers.hcurl_m6b_w6a_multi_order_range import (
        W6AMultiOrderRangeDiagnostic,
        load_w1a_legacy_basis,
    )

    raw_dir = Path(raw_dir).resolve()
    watchdog_summary_path = Path(watchdog_summary_path).resolve()
    watchdog_dir = watchdog_summary_path.parent
    legacy_store_dir = Path(legacy_store_dir).resolve()
    w5_raw_dir = Path(w5_raw_dir).resolve()
    jit_cache_source = Path(jit_cache_source).resolve()
    summary: Mapping[str, Any] = {}
    watchdog: Mapping[str, Any] = {}
    problems: list[str] = []
    try:
        checker_source_start = h2b._light_source()
    except (OSError, RuntimeError, TypeError, ValueError):
        checker_source_start = {}
    try:
        summary = _read_json(raw_dir / "w6a_summary.json")
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        problems.append(f"summary:{type(exc).__name__}")
    try:
        watchdog = _read_json(watchdog_summary_path)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        problems.append(f"watchdog:{type(exc).__name__}")

    w5_authority: dict[str, Any] | None = None
    checker_runtime: dict[str, Any] = {}
    runtime_identity_ok = False
    try:
        w5_authority = _m6b_w6a_w5_compact_authority()
        frozen_compiler = w5_authority["factor_compiler"]
        from mpi4py import MPI

        checker_runtime = _m6b_runtime_identity(
            h2b,
            h2b._lazy_h2a(),
            MPI.COMM_WORLD,
            compiler_probe=False,
            compiler=frozen_compiler,
        )
        producer_runtime = summary.get("runtime_identity") if isinstance(summary, Mapping) else None
        runtime_identity_ok = bool(
            _m6b_w6a_runtime_valid(
                producer_runtime, frozen_compiler=frozen_compiler
            )
            and _m6b_w6a_runtime_valid(
                checker_runtime, frozen_compiler=frozen_compiler
            )
            and producer_runtime == checker_runtime
        )
    except (ImportError, OSError, RuntimeError, TypeError, ValueError, KeyError):
        problems.append("runtime_identity")

    progress = _m6b_w6a_progress_valid(raw_dir / "w6a_progress.jsonl")
    timeline_name = f"{M6B_W6A_PHASE}_timeline.jsonl"
    timeline = _m6b_w6a_timeline_valid(watchdog_dir / timeline_name)
    store_validation: dict[str, Any] = {"pass": False, "problems": ["not_checked"]}
    numeric: dict[str, Any] = {"pass": False, "problems": ["not_checked"]}
    actual_prediction: dict[str, Any] | None = None
    actual_store_audit: Mapping[str, Any] | None = None
    residual_artifacts = summary.get("residual_artifacts") if isinstance(summary, Mapping) else None
    if isinstance(summary, Mapping):
        store = None
        try:
            store = W6AMultiOrderRangeDiagnostic.load(
                raw_dir / "sparse_range_store/manifest.json",
                legacy_store_dir=legacy_store_dir,
            )
            actual_store_audit = dict(store.audit)
            legacy_authority = load_w1a_legacy_basis(legacy_store_dir)
            legacy_audit = legacy_authority["audit"]
            actual_prediction = _m6b_w6a_predicted_live_set(
                old_retained_bytes=int(legacy_audit["retained_total_bytes"]),
                new_retained_bytes=(
                    int(actual_store_audit["retained_z_r_bytes"])
                    + M6B_W6A_MANIFEST_RESERVE_BYTES
                ),
                old_work_bytes=int(legacy_audit["bounded_work_bytes"]),
                new_work_bytes=int(actual_store_audit["bounded_work_bytes"]),
            )
            store_validation = {
                "pass": True,
                "problems": [],
                "audit": actual_store_audit,
                "factor_audit": actual_store_audit["factor_audit"],
            }
            if isinstance(residual_artifacts, Mapping):
                observed: dict[str, dict[str, float]] = {}
                for iteration in M6B_W6A_W5_RESIDUAL_ITERATIONS:
                    path = raw_dir / f"m6b_w6a_residual_iter{iteration}.npy"
                    values = np.load(path, allow_pickle=False, mmap_mode="r")
                    result = store.compare_range_orders(values)
                    observed[str(iteration)] = {
                        "rho75": float(result["rho75"]),
                        "rho390": float(result["rho390"]),
                    }
                numeric = _m6b_w6a_numeric_gate(observed)
        except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
            store_validation = {"pass": False, "problems": [f"store:{type(exc).__name__}"]}
            numeric = {"pass": False, "problems": [f"numeric:{type(exc).__name__}"]}
        finally:
            if store is not None:
                store.close()

    residual_files_ok = _m6b_w6a_w5_residual_files_valid(
        residual_artifacts,
        raw_dir,
        w5_raw_dir,
        compact_record=None if w5_authority is None else w5_authority["record"],
    )

    prediction = summary.get("prediction") if isinstance(summary, Mapping) else None
    scope_ok = False
    if isinstance(prediction, Mapping):
        try:
            scope_ok = summary.get("scope") == _m6b_w6a_scope(
                prediction=_m6b_w6a_predicted_live_set(
                    old_retained_bytes=prediction["old_retained_bytes"],
                    new_retained_bytes=prediction["new_retained_bytes"],
                    old_work_bytes=prediction["old_work_bytes"],
                    new_work_bytes=prediction["new_work_bytes"],
                )
            )
        except (KeyError, TypeError, ValueError):
            scope_ok = False
    producer_source_start = summary.get("source_at_start") if isinstance(summary, Mapping) else None
    producer_source_end = summary.get("source_at_end") if isinstance(summary, Mapping) else None
    source_ok = bool(
        isinstance(producer_source_start, Mapping)
        and isinstance(producer_source_end, Mapping)
        and producer_source_start.get("source_commit_full_sha") == expected_source_sha
        and producer_source_end.get("source_commit_full_sha") == expected_source_sha
        and _m6b_w6a_source_valid(producer_source_start)
        and _m6b_w6a_source_valid(producer_source_end)
    )
    jit = summary.get("jit_cache") if isinstance(summary, Mapping) else None
    jit_ok = _m6b_w6a_jit_cache_valid(
        jit,
        h2b,
        jit_cache_source,
        raw_dir / "jit_cache",
    )
    inventory_ok = _m6b_w6a_artifact_inventory_valid(
        watchdog.get("artifact_inventory") if isinstance(watchdog, Mapping) else None,
        raw_dir,
        watchdog_dir,
    )
    watchdog_contract_ok = _m6b_w6a_watchdog_contract_valid(
        watchdog,
        raw_dir=raw_dir,
        legacy_store_dir=legacy_store_dir,
        w5_raw_dir=w5_raw_dir,
        jit_cache_source=jit_cache_source,
        expected_source_sha=expected_source_sha,
    )
    gate = _m6b_w6a_formal_gate(
        summary={
            **dict(summary),
            "scope": summary.get("scope") if isinstance(summary, Mapping) else None,
            "prediction": prediction,
            "source_at_start": summary.get("source_at_start") if isinstance(summary, Mapping) else None,
            "source_at_end": summary.get("source_at_end") if isinstance(summary, Mapping) else None,
            "carrier_audit": summary.get("carrier_audit") if isinstance(summary, Mapping) else None,
            "architecture": summary.get("architecture") if isinstance(summary, Mapping) else None,
        },
        watchdog=watchdog,
        progress=progress,
        timeline=timeline,
        store_validation=store_validation,
        numeric=numeric,
        artifact_inventory_ok=inventory_ok,
        residual_files_ok=residual_files_ok,
        watchdog_contract_ok=watchdog_contract_ok,
        expected_source_sha=expected_source_sha,
        runtime_identity_ok=runtime_identity_ok,
        actual_prediction=actual_prediction,
        actual_store_audit=actual_store_audit,
    )
    try:
        checker_source_end = h2b._light_source()
    except (OSError, RuntimeError, TypeError, ValueError):
        checker_source_end = {}
    checker_source_ok = bool(
        _m6b_w6a_source_valid(checker_source_start)
        and _m6b_w6a_source_valid(checker_source_end)
        and checker_source_start.get("source_commit_full_sha") == expected_source_sha
        and checker_source_end.get("source_commit_full_sha") == expected_source_sha
    )
    checks = {
        **gate["checks"],
        "w5_compact_authority": w5_authority is not None and residual_files_ok,
        "producer_source_binding": source_ok,
        "scope": scope_ok,
        "jit": jit_ok,
        "checker_source": checker_source_ok,
    }
    if not isinstance(summary, Mapping) or summary.get("schema") != M6B_W6A_SCHEMA:
        checks["summary_schema"] = False
    else:
        checks["summary_schema"] = _evidence_valid(summary)
    problems.extend(name for name, passed in checks.items() if not passed)
    result = {
        "schema": M6B_W6A_FORMAL_CHECK_SCHEMA,
        "status": "pass" if all(checks.values()) else "gate_failed",
        "classification": "PASS" if all(checks.values()) else "FORMAL_GATE_FAILED",
        "checks": checks,
        "problems": sorted(set(problems + list(store_validation.get("problems", [])) + list(numeric.get("problems", [])))),
        "numeric_gate": numeric,
        "store_validation": store_validation,
        "progress": progress,
        "timeline": timeline,
        "producer_source_sha": expected_source_sha,
        "checker_source_at_start": checker_source_start,
        "checker_source_at_end": checker_source_end,
        "runtime_identity": {
            "producer": summary.get("runtime_identity")
            if isinstance(summary, Mapping)
            else None,
            "checker": checker_runtime,
            "match": runtime_identity_ok,
        },
        "checker_runtime_identity": checker_runtime,
        "w5_compact_authority": None
        if w5_authority is None
        else {
            "path": w5_authority["path"],
            "file_sha256": w5_authority["file_sha256"],
            "producer_source_sha": w5_authority["record"]["producer_source_sha"],
        },
        "formal_pass": all(checks.values()),
        "pde_pass": False,
        "official_rta": False,
        "producer_summary": _artifact(raw_dir, "w6a_summary.json"),
        "watchdog_summary": _artifact(watchdog_dir, watchdog_summary_path.name),
    }
    _write_json(output, _attach_evidence(result))
    return 0 if result["formal_pass"] else 1


def _check_command(run_dir: Path, output: Path) -> int:
    checks: dict[str, bool] = {
        "watchdog": False,
        "worker_summary": False,
        "worker_payload": False,
        "checkpoint_arrays": False,
        "raw_inventory": False,
        "command_identity": False,
        "initial_prediction": False,
        "dynamic_prediction": False,
        "phase_lifecycle": False,
        "builder_summary": False,
        "watchdog_phase_source_identity": False,
        "worker_phase_source_identity": False,
        "checker_source_identity": False,
        "shared_volume_kernel": False,
        "material_tag_coverage": False,
    }
    problems: list[str] = []
    watchdog_path = run_dir / "m6b_watchdog_summary.json"
    worker_path = run_dir / "m6b_worker_summary.json"
    watchdog: dict[str, Any] | None = None
    worker: dict[str, Any] | None = None
    checker_h2b: Any | None = None
    checker_source_start: Mapping[str, Any] | None = None
    checker_source_end: Mapping[str, Any] | None = None
    phase_source_identity_for_check: Mapping[str, Any] | None = None
    try:
        checker_h2b = __import__(
            "benchmarks.run_task037_extra_h2b", fromlist=["_light_source"]
        )
        checker_source_start = checker_h2b._light_source()
    except (ImportError, OSError, RuntimeError, TypeError, ValueError) as exc:
        problems.append(f"checker_source_start:{type(exc).__name__}")
    try:
        watchdog = _read_json(watchdog_path)
        watchdog_start = watchdog.get("source_at_start")
        watchdog_end = watchdog.get("source_at_end")
        watchdog_source_pair = bool(
            isinstance(watchdog_start, Mapping)
            and isinstance(watchdog_end, Mapping)
            and watchdog_start.get("source_commit_full_sha")
            == watchdog_end.get("source_commit_full_sha")
            and watchdog_start.get("tracked_source_dirty") is False
            and watchdog_end.get("tracked_source_dirty") is False
        )
        stage_summary_for_check = _read_json(run_dir / "m6b_stage_summary.json")
        builder_summary_for_check = _read_json(
            run_dir / "m6b_builder_summary.json"
        )
        online_summary_for_check = _read_json(
            run_dir / "m6b_mpi1_worker_summary.json"
        )
        phase_source_identity_for_check = _m6b_phase_source_identity(
            {
                "stage": stage_summary_for_check,
                "builder": builder_summary_for_check,
                "online": online_summary_for_check,
                "watchdog": {
                    "source_at_start": watchdog_start,
                    "source_at_end": watchdog_end,
                },
            }
        )
        checks["watchdog"] = bool(
            watchdog.get("schema") == M6B_WATCHDOG_SCHEMA
            and _evidence_valid(watchdog)
            and watchdog.get("status") == "measurement_complete"
            and watchdog.get("pass") is True
            and watchdog.get("scope") == _m6b_scope()
            and watchdog.get("predicted_live_set") == _predicted_live_set()
            and isinstance(watchdog.get("predicted_live_set"), Mapping)
            and watchdog["predicted_live_set"].get("gate") is True
            and watchdog.get("phase_gates") == {
                "stage": True,
                "builder": True,
                "online": True,
            }
            and watchdog_source_pair
            and watchdog.get("phase_source_identity") == phase_source_identity_for_check
            and phase_source_identity_for_check["pass"] is True
            and watchdog_start.get("source_commit_full_sha")
            == phase_source_identity_for_check["source_commit_full_sha"]
        )
        builder_factor_audit_for_check = builder_summary_for_check["factor_audit"]
        expected_dynamic_prediction = _dynamic_predicted_live_set(
            builder_factor_audit_for_check["retained_total_bytes"]
        )
        checks["initial_prediction"] = bool(
            watchdog.get("predicted_live_set") == _predicted_live_set()
            and isinstance(watchdog.get("predicted_live_set"), Mapping)
            and watchdog["predicted_live_set"].get("gate") is True
        )
        checks["dynamic_prediction"] = bool(
            watchdog.get("dynamic_predicted_live_set") == expected_dynamic_prediction
            and isinstance(watchdog.get("dynamic_predicted_live_set"), Mapping)
            and watchdog["dynamic_predicted_live_set"].get("gate") is True
        )
        checks["builder_summary"] = _m6b_builder_summary_valid(
            builder_summary_for_check
        )
        stage_kernel_for_check = (
            stage_summary_for_check.get("forms", {}).get("shared_volume_kernel")
            if isinstance(stage_summary_for_check.get("forms"), Mapping)
            else None
        )
        builder_kernel_for_check = builder_summary_for_check.get(
            "shared_volume_kernel"
        )
        online_measurement_for_check = online_summary_for_check.get("measurement")
        online_kernel_for_check = (
            online_measurement_for_check.get("shared_volume_kernel")
            if isinstance(online_measurement_for_check, Mapping)
            else None
        )
        stage_forms_for_check = stage_summary_for_check.get("forms")
        online_forms_for_check = (
            online_measurement_for_check.get("form")
            if isinstance(online_measurement_for_check, Mapping)
            else None
        )
        identity_keys = (
            "operator_identity",
            "representation",
            "fixed_physics",
            "module_name",
            "ufl_signature",
            "ufcx_signature",
        )
        checks["shared_volume_kernel"] = bool(
            _m6b_shared_kernel_valid(stage_kernel_for_check, phase="stage")
            and _m6b_shared_kernel_valid(builder_kernel_for_check, phase="builder")
            and _m6b_shared_kernel_valid(online_kernel_for_check, phase="mpi1")
            and isinstance(stage_forms_for_check, Mapping)
            and _m6b_form_records_bound(
                stage_forms_for_check.get("outer_volume"),
                stage_forms_for_check.get("shifted_volume"),
                stage_kernel_for_check,
                phase="stage",
            )
            and _m6b_form_record_bound(
                builder_summary_for_check.get("form"),
                builder_kernel_for_check,
                role="shifted_volume",
                beta=M6B_BETA,
                code_state="hit_no_new_decl_impl",
                shared_phase="stage",
            )
            and isinstance(online_forms_for_check, Mapping)
            and _m6b_form_records_bound(
                online_forms_for_check.get("outer_volume"),
                online_forms_for_check.get("shifted_volume"),
                online_kernel_for_check,
                phase="mpi1",
            )
            and builder_kernel_for_check == stage_kernel_for_check
            and all(
                online_kernel_for_check[key] == stage_kernel_for_check[key]
                for key in identity_keys
            )
        )
        checks["material_tag_coverage"] = bool(
            isinstance(stage_forms_for_check, Mapping)
            and _m6b_material_tag_coverage_valid(
                stage_forms_for_check.get("material_tag_coverage"),
                owned_cells=M6B_GLOBAL_CELLS,
            )
            and _m6b_material_tag_coverage_valid(
                builder_summary_for_check.get("material_tag_coverage"),
                owned_cells=M6B_GLOBAL_CELLS,
            )
            and isinstance(online_measurement_for_check, Mapping)
            and _m6b_material_tag_coverage_valid(
                online_measurement_for_check.get("material_tag_coverage"),
                owned_cells=M6B_GLOBAL_CELLS,
            )
        )
        phase_records = watchdog["phases"]
        phase_specs = (
            ("stage", False, False, M6B_STAGE_TIMEOUT_SECONDS),
            ("builder", False, True, M6B_BUILDER_TIMEOUT_SECONDS),
            ("online", True, True, M6B_ONLINE_TIMEOUT_SECONDS),
        )
        checks["phase_lifecycle"] = bool(
            isinstance(phase_records, Mapping)
            and all(
                isinstance(phase_records[name], Mapping)
                and _m6b_lifecycle_valid(
                    phase_records[name],
                    online=online,
                    require_compiler_empty=require_compiler_empty,
                )
                and phase_records[name]["timeout_seconds"] == timeout_seconds
                for name, online, require_compiler_empty, timeout_seconds in phase_specs
            )
        )
        checks["watchdog_phase_source_identity"] = bool(
            watchdog.get("phase_source_identity") == phase_source_identity_for_check
        )
        expected_commands = {
            name: _m6b_command(command, run_dir)
            for name, command in (
                ("stage", "m6b-stage-worker"),
                ("builder", "m6b-builder"),
                ("online", "m6b-worker"),
            )
        }
        checks["command_identity"] = watchdog.get("command_identity") == expected_commands
        checks["raw_inventory"] = watchdog.get("raw_artifacts") == _m6b_raw_artifacts(
            run_dir, _read_json(worker_path) if worker_path.is_file() else None
        )
        worker = _read_json(worker_path)
        checks["worker_summary"] = bool(
            worker.get("schema") == M6B_WORKER_SCHEMA
            and _evidence_valid(worker)
            and watchdog.get("worker_summary") == _artifact(run_dir, worker_path.name)
        )
        checks["worker_phase_source_identity"] = bool(
            checks["worker_summary"]
            and worker.get("phase_source_identity")
            == watchdog.get("phase_source_identity")
        )
        if checks["worker_summary"]:
            worker_checks = _m6b_check_payload(worker)
            checks["worker_payload"] = worker_checks["pass"] is True
            checkpoint = _m6b_checkpoint_recompute(
                run_dir, worker.get("screen")
            )
            checks["checkpoint_arrays"] = checkpoint["pass"] is True
            problems.extend(worker_checks["problems"])
            problems.extend(checkpoint["problems"])
        else:
            worker_checks = {"checks": {}, "problems": ["worker_summary_invalid"]}
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        worker_checks = {"checks": {}, "problems": [f"raw_unreadable:{type(exc).__name__}"]}
        problems.append(f"raw_unreadable:{type(exc).__name__}")
    if checker_h2b is not None and checker_source_start is not None:
        checker_source_end = checker_h2b._light_source()
        checks["checker_source_identity"] = bool(
            checker_h2b._source_pair_valid(checker_source_start, checker_source_end)
            and isinstance(phase_source_identity_for_check, Mapping)
            and phase_source_identity_for_check.get("pass") is True
            and checker_source_start.get("source_commit_full_sha")
            == phase_source_identity_for_check.get("source_commit_full_sha")
            and checker_source_end.get("source_commit_full_sha")
            == phase_source_identity_for_check.get("source_commit_full_sha")
        )
    for name, passed in checks.items():
        if not passed:
            problems.append(name)
    result = {
        "schema": M6B_CHECK_SCHEMA,
        "status": "pass" if all(checks.values()) else "gate_failed",
        "pass": all(checks.values()),
        "checks": {**checks, **worker_checks.get("checks", {})},
        "problems": sorted(set(problems)),
        "predicted_live_set": _predicted_live_set(),
        "watchdog": _artifact(run_dir, watchdog_path.name),
        "worker_summary": _artifact(run_dir, worker_path.name),
        "dynamic_predicted_live_set": watchdog.get("dynamic_predicted_live_set")
        if isinstance(watchdog, Mapping)
        else None,
        "checker_source": {
            "start": checker_source_start,
            "end": checker_source_end,
        },
        "worker_source": None if worker is None else {
            "start": worker.get("source_at_start"),
            "end": worker.get("source_at_end"),
        },
    }
    _write_json(output, _attach_evidence(result))
    return 0 if result["pass"] else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in (
        "m6b-stage-worker",
        "m6b-builder",
        "m6b-worker",
        "m6b-watchdog",
        "m6b-w1-builder",
        "m6b-w2-diagnostic",
        "m6b-w2r-diagnostic",
        "m6b-w3-screen",
        "m6b-w3-beta05-screen",
        "m6b-w4-fbcgs-screen",
        "m6b-w5-disk-fgmres-screen",
        "m6b-w7-s1-screen",
        "m6b-w6a-builder",
        "m6b-w6a-watchdog",
        "m6b-w8a-builder",
        "m6b-w8a-watchdog",
        "m6b-w8a-companion",
        "m6b-w8a-companion-watchdog",
    ):
        item = sub.add_parser(command)
        item.add_argument("--run-dir", required=True)
        if command == "m6b-w1-builder":
            item.add_argument("--jit-cache-source", required=True)
        if command == "m6b-w6a-builder":
            item.add_argument("--legacy-store-dir", required=True)
            item.add_argument("--w5-raw-dir", required=True)
            item.add_argument("--jit-cache-source", required=True)
            item.add_argument(
                "--expected-source-sha",
                required=True,
                type=_m6b_w2_source_sha_argument,
            )
        if command == "m6b-w6a-watchdog":
            item.add_argument("--watchdog-dir", required=True)
            item.add_argument("--legacy-store-dir", required=True)
            item.add_argument("--w5-raw-dir", required=True)
            item.add_argument("--jit-cache-source", required=True)
            item.add_argument(
                "--expected-source-sha",
                required=True,
                type=_m6b_w2_source_sha_argument,
            )
        if command == "m6b-w8a-builder":
            item.add_argument("--w6a-raw-dir", required=True)
            item.add_argument("--jit-cache-source", required=True)
            item.add_argument(
                "--expected-source-sha",
                required=True,
                type=_m6b_w2_source_sha_argument,
            )
        if command == "m6b-w8a-watchdog":
            item.add_argument("--watchdog-dir", required=True)
            item.add_argument("--w6a-raw-dir", required=True)
            item.add_argument("--jit-cache-source", required=True)
            item.add_argument(
                "--expected-source-sha",
                required=True,
                type=_m6b_w2_source_sha_argument,
            )
        if command == "m6b-w8a-companion":
            item.add_argument("--w8a-raw-dir", required=True)
            item.add_argument("--w6a-raw-dir", required=True)
            item.add_argument("--jit-cache-source", required=True)
            item.add_argument(
                "--expected-source-sha",
                required=True,
                type=_m6b_w2_source_sha_argument,
            )
        if command == "m6b-w8a-companion-watchdog":
            item.add_argument("--watchdog-dir", required=True)
            item.add_argument("--w8a-raw-dir", required=True)
            item.add_argument("--w6a-raw-dir", required=True)
            item.add_argument("--jit-cache-source", required=True)
            item.add_argument(
                "--expected-source-sha",
                required=True,
                type=_m6b_w2_source_sha_argument,
            )
        if command in {
            "m6b-w2-diagnostic",
            "m6b-w2r-diagnostic",
            "m6b-w3-screen",
            "m6b-w3-beta05-screen",
            "m6b-w4-fbcgs-screen",
            "m6b-w5-disk-fgmres-screen",
            "m6b-w7-s1-screen",
        }:
            item.add_argument("--factor-authority-dir", required=True)
            item.add_argument("--wave-authority-dir", required=True)
            item.add_argument("--jit-cache-source", required=True)
            item.add_argument(
                "--expected-source-sha",
                required=True,
                type=_m6b_w2_source_sha_argument,
            )
            item.add_argument("--w0-authority-file", required=True)
            if command == "m6b-w7-s1-screen":
                item.add_argument("--w5-compact", required=True)
                item.add_argument("--w5-raw-dir", required=True)
    check = sub.add_parser("m6b-check")
    check.add_argument("--run-dir", required=True)
    check.add_argument("--output", required=True)
    w5_check = sub.add_parser("m6b-w5-check")
    w5_check.add_argument("--raw-dir", required=True)
    w5_check.add_argument("--watchdog-summary", required=True)
    w5_check.add_argument("--output", required=True)
    w5_check.add_argument(
        "--expected-producer-sha",
        required=True,
        type=_m6b_w2_source_sha_argument,
    )
    w7_check = sub.add_parser("m6b-w7-s1-check")
    w7_check.add_argument("--raw-dir", required=True)
    w7_check.add_argument("--watchdog-summary", required=True)
    w7_check.add_argument("--w5-compact", required=True)
    w7_check.add_argument("--w5-raw-dir", required=True)
    w7_check.add_argument("--jit-cache-source", required=True)
    w7_check.add_argument("--output", required=True)
    w7_check.add_argument(
        "--expected-source-sha",
        required=True,
        type=_m6b_w2_source_sha_argument,
    )
    w6a_check = sub.add_parser("m6b-w6a-check")
    w6a_check.add_argument("--raw-dir", required=True)
    w6a_check.add_argument("--legacy-store-dir", required=True)
    w6a_check.add_argument("--output", required=True)
    w6a_check.add_argument(
        "--expected-source-sha",
        required=True,
        type=_m6b_w2_source_sha_argument,
    )
    w6a_formal = sub.add_parser("m6b-w6a-formal-check")
    w6a_formal.add_argument("--raw-dir", required=True)
    w6a_formal.add_argument("--watchdog-summary", required=True)
    w6a_formal.add_argument("--legacy-store-dir", required=True)
    w6a_formal.add_argument("--w5-raw-dir", required=True)
    w6a_formal.add_argument("--jit-cache-source", required=True)
    w6a_formal.add_argument("--output", required=True)
    w6a_formal.add_argument(
        "--expected-source-sha",
        required=True,
        type=_m6b_w2_source_sha_argument,
    )
    w6b_s0 = sub.add_parser("m6b-w6b-s0")
    w6b_s0.add_argument("--w6a-raw-dir", required=True)
    w6b_s0.add_argument("--w5-raw-dir", required=True)
    w6b_s0.add_argument("--output", required=True)
    w6b_s0.add_argument(
        "--expected-source-sha",
        required=True,
        type=_m6b_w2_source_sha_argument,
    )
    w8a_formal = sub.add_parser("m6b-w8a-formal-check")
    w8a_formal.add_argument("--raw-dir", required=True)
    w8a_formal.add_argument("--watchdog-summary", required=True)
    w8a_formal.add_argument("--w6a-raw-dir", required=True)
    w8a_formal.add_argument("--jit-cache-source", required=True)
    w8a_formal.add_argument("--output", required=True)
    w8a_formal.add_argument(
        "--expected-source-sha", required=True, type=_m6b_w2_source_sha_argument
    )
    w8a_recovery = sub.add_parser("m6b-w8a-recover")
    w8a_recovery.add_argument("--raw-dir", required=True)
    w8a_recovery.add_argument("--watchdog-dir", required=True)
    w8a_recovery.add_argument("--w6a-raw-dir", required=True)
    w8a_recovery.add_argument("--jit-cache-source", required=True)
    w8a_recovery.add_argument("--companion-summary", required=True)
    w8a_recovery.add_argument("--companion-watchdog-summary", required=True)
    w8a_recovery.add_argument("--output", required=True)
    w8a_recovery.add_argument(
        "--expected-producer-sha", required=True, type=_m6b_w2_source_sha_argument
    )
    w8a_recovery.add_argument(
        "--expected-companion-source-sha", required=True, type=_m6b_w2_source_sha_argument
    )
    w8b_s0 = sub.add_parser("m6b-w8b-s0")
    w8b_s0.add_argument("--w8a-raw-dir", required=True)
    w8b_s0.add_argument("--w8a-formal-output", required=True)
    w8b_s0.add_argument("--w6a-raw-dir", required=True)
    w8b_s0.add_argument("--w5-raw-dir", required=True)
    w8b_s0.add_argument("--w7-raw-dir", required=True)
    w8b_s0.add_argument("--w5-compact", required=True)
    w8b_s0.add_argument("--w7-compact", required=True)
    w8b_s0.add_argument("--output", required=True)
    w8b_s0.add_argument(
        "--expected-source-sha", required=True, type=_m6b_w2_source_sha_argument
    )
    w9a = sub.add_parser("m6b-w9a-check")
    w9a.add_argument("--w5-raw-dir", required=True)
    w9a.add_argument("--w5-compact", required=True)
    w9a.add_argument("--w7-raw-dir", required=True)
    w9a.add_argument("--w7-compact", required=True)
    w9a.add_argument("--output", required=True)
    w9a.add_argument(
        "--expected-source-sha", required=True, type=_m6b_w2_source_sha_argument
    )
    w10a = sub.add_parser("m6b-w10a-check")
    w10a.add_argument("--w5-raw-dir", required=True)
    w10a.add_argument("--w5-compact", required=True)
    w10a.add_argument("--w7-raw-dir", required=True)
    w10a.add_argument("--w7-compact", required=True)
    w10a.add_argument("--output", required=True)
    w10a.add_argument(
        "--expected-source-sha", required=True, type=_m6b_w2_source_sha_argument
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "m6b-w5-check":
        return _m6b_w5_check_command(
            Path(args.raw_dir).resolve(),
            Path(args.watchdog_summary).resolve(),
            Path(args.output).resolve(),
            args.expected_producer_sha,
        )
    if args.command == "m6b-w7-s1-check":
        return _m6b_w7_s1_check_command(
            Path(args.raw_dir).resolve(),
            Path(args.watchdog_summary).resolve(),
            Path(args.w5_compact).resolve(),
            Path(args.w5_raw_dir).resolve(),
            Path(args.jit_cache_source).resolve(),
            Path(args.output).resolve(),
            args.expected_source_sha,
        )
    if args.command == "m6b-w6a-check":
        return _m6b_w6a_check_command(
            Path(args.raw_dir).resolve(),
            Path(args.legacy_store_dir).resolve(),
            Path(args.output).resolve(),
            args.expected_source_sha,
        )
    if args.command == "m6b-w6a-formal-check":
        return _m6b_w6a_formal_check_command(
            Path(args.raw_dir).resolve(),
            Path(args.watchdog_summary).resolve(),
            Path(args.legacy_store_dir).resolve(),
            Path(args.w5_raw_dir).resolve(),
            Path(args.jit_cache_source).resolve(),
            Path(args.output).resolve(),
            args.expected_source_sha,
        )
    if args.command == "m6b-w6b-s0":
        return _run_m6b_w6b_s0(
            Path(args.w6a_raw_dir).resolve(),
            Path(args.w5_raw_dir).resolve(),
            Path(args.output).resolve(),
            args.expected_source_sha,
        )
    if args.command == "m6b-w8a-formal-check":
        return _run_m6b_w8a_formal_check(
            Path(args.raw_dir).resolve(),
            Path(args.watchdog_summary).resolve(),
            Path(args.w6a_raw_dir).resolve(),
            Path(args.jit_cache_source).resolve(),
            Path(args.output).resolve(),
            args.expected_source_sha,
        )
    if args.command == "m6b-w8a-recover":
        return _run_m6b_w8a_recovery(
            Path(args.raw_dir).resolve(),
            Path(args.watchdog_dir).resolve(),
            Path(args.w6a_raw_dir).resolve(),
            Path(args.jit_cache_source).resolve(),
            Path(args.output).resolve(),
            args.expected_producer_sha,
            Path(args.companion_summary).resolve(),
            Path(args.companion_watchdog_summary).resolve(),
            args.expected_companion_source_sha,
        )
    if args.command == "m6b-w8b-s0":
        return _run_m6b_w8b_s0(
            Path(args.w8a_raw_dir).resolve(),
            Path(args.w8a_formal_output).resolve(),
            Path(args.w6a_raw_dir).resolve(),
            Path(args.w5_raw_dir).resolve(),
            Path(args.w7_raw_dir).resolve(),
            Path(args.w5_compact).resolve(),
            Path(args.w7_compact).resolve(),
            Path(args.output).resolve(),
            args.expected_source_sha,
        )
    if args.command == "m6b-w9a-check":
        return _run_m6b_w9a_check(
            Path(args.w5_raw_dir).resolve(),
            Path(args.w5_compact).resolve(),
            Path(args.w7_raw_dir).resolve(),
            Path(args.w7_compact).resolve(),
            Path(args.output).resolve(),
            args.expected_source_sha,
        )
    if args.command == "m6b-w10a-check":
        return _run_m6b_w10a_check(
            Path(args.w5_raw_dir).resolve(),
            Path(args.w5_compact).resolve(),
            Path(args.w7_raw_dir).resolve(),
            Path(args.w7_compact).resolve(),
            Path(args.output).resolve(),
            args.expected_source_sha,
        )
    run_dir = Path(args.run_dir).resolve()
    if args.command == "m6b-check":
        return _check_command(run_dir, Path(args.output).resolve())
    if args.command == "m6b-stage-worker":
        return _run_m6b_stage_worker(run_dir)
    if args.command == "m6b-builder":
        return _run_m6b_builder(run_dir)
    if args.command == "m6b-worker":
        return _run_m6b_online_worker(run_dir)
    if args.command == "m6b-watchdog":
        return _run_m6b_watchdog(run_dir)
    if args.command == "m6b-w1-builder":
        return _run_m6b_w1_builder(run_dir, Path(args.jit_cache_source).resolve())
    if args.command == "m6b-w6a-builder":
        return _run_m6b_w6a_builder(
            run_dir,
            Path(args.legacy_store_dir).resolve(),
            Path(args.w5_raw_dir).resolve(),
            Path(args.jit_cache_source).resolve(),
            args.expected_source_sha,
        )
    if args.command == "m6b-w6a-watchdog":
        return _run_m6b_w6a_watchdog(
            run_dir,
            Path(args.watchdog_dir).resolve(),
            Path(args.legacy_store_dir).resolve(),
            Path(args.w5_raw_dir).resolve(),
            Path(args.jit_cache_source).resolve(),
            args.expected_source_sha,
        )
    if args.command == "m6b-w8a-builder":
        return _run_m6b_w8a_builder(
            run_dir,
            Path(args.w6a_raw_dir).resolve(),
            Path(args.jit_cache_source).resolve(),
            args.expected_source_sha,
        )
    if args.command == "m6b-w8a-watchdog":
        return _run_m6b_w8a_watchdog(
            run_dir,
            Path(args.watchdog_dir).resolve(),
            Path(args.w6a_raw_dir).resolve(),
            Path(args.jit_cache_source).resolve(),
            args.expected_source_sha,
        )
    if args.command == "m6b-w8a-companion":
        return _run_m6b_w8a_companion(
            run_dir,
            Path(args.w8a_raw_dir).resolve(),
            Path(args.w6a_raw_dir).resolve(),
            Path(args.jit_cache_source).resolve(),
            args.expected_source_sha,
        )
    if args.command == "m6b-w8a-companion-watchdog":
        return _run_m6b_w8a_companion_watchdog(
            run_dir,
            Path(args.watchdog_dir).resolve(),
            Path(args.w8a_raw_dir).resolve(),
            Path(args.w6a_raw_dir).resolve(),
            Path(args.jit_cache_source).resolve(),
            args.expected_source_sha,
        )
    if args.command == "m6b-w2-diagnostic":
        return _run_m6b_w2_diagnostic(
            run_dir,
            Path(args.factor_authority_dir).resolve(),
            Path(args.wave_authority_dir).resolve(),
            Path(args.jit_cache_source).resolve(),
            args.expected_source_sha,
            Path(args.w0_authority_file).resolve(),
        )
    if args.command == "m6b-w2r-diagnostic":
        return _run_m6b_w2r_diagnostic(
            run_dir,
            Path(args.factor_authority_dir).resolve(),
            Path(args.wave_authority_dir).resolve(),
            Path(args.jit_cache_source).resolve(),
            args.expected_source_sha,
            Path(args.w0_authority_file).resolve(),
        )
    if args.command == "m6b-w3-screen":
        return _run_m6b_w3_screen(
            run_dir,
            Path(args.factor_authority_dir).resolve(),
            Path(args.wave_authority_dir).resolve(),
            Path(args.jit_cache_source).resolve(),
            args.expected_source_sha,
            Path(args.w0_authority_file).resolve(),
        )
    if args.command == "m6b-w3-beta05-screen":
        return _run_m6b_w3_beta05_screen(
            run_dir,
            Path(args.factor_authority_dir).resolve(),
            Path(args.wave_authority_dir).resolve(),
            Path(args.jit_cache_source).resolve(),
            args.expected_source_sha,
            Path(args.w0_authority_file).resolve(),
        )
    if args.command == "m6b-w4-fbcgs-screen":
        return _run_m6b_w4_fbcgs_screen(
            run_dir,
            Path(args.factor_authority_dir).resolve(),
            Path(args.wave_authority_dir).resolve(),
            Path(args.jit_cache_source).resolve(),
            args.expected_source_sha,
            Path(args.w0_authority_file).resolve(),
        )
    if args.command == "m6b-w5-disk-fgmres-screen":
        return _run_m6b_w5_disk_fgmres_screen(
            run_dir,
            Path(args.factor_authority_dir).resolve(),
            Path(args.wave_authority_dir).resolve(),
            Path(args.jit_cache_source).resolve(),
            args.expected_source_sha,
            Path(args.w0_authority_file).resolve(),
        )
    if args.command == "m6b-w7-s1-screen":
        return _run_m6b_w7_s1_screen(
            run_dir,
            Path(args.factor_authority_dir).resolve(),
            Path(args.wave_authority_dir).resolve(),
            Path(args.jit_cache_source).resolve(),
            args.expected_source_sha,
            Path(args.w0_authority_file).resolve(),
            Path(args.w5_compact).resolve(),
            Path(args.w5_raw_dir).resolve(),
        )
    raise ValueError(f"unknown M6B command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
