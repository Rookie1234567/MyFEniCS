from __future__ import annotations

from collections import Counter
import math
from typing import Any


TASK035D_CASE097_BACKEND = "assembly_time_variable_p_condensed"
TASK035D_CASE097_PLAN_SCHEMA = (
    "task035d.variable-p-cell-degree-plan.v1"
)
TASK035D_CASE097_AUTHORITY_SCHEMA = (
    "task035d.legacy-seeded-plan-authority.v1"
)
TASK035D_T30_PLAN_NAME = "t30"
TASK035D_T30_PLAN_PATH = (
    "benchmarks/cases/"
    "097_goal_oriented_exact_sequence_hp_adaptivity/records/"
    "t30_h10_cell_degree_plan_v1.json"
)
TASK035D_T30_PLAN_FILE_SHA256 = (
    "4f580a06f4c1774316ecbdce950828b3cda143f0807145d9d40de2cd64df5c3a"
)
TASK035D_T30_AUTHORITY_PATH = (
    "benchmarks/cases/"
    "097_goal_oriented_exact_sequence_hp_adaptivity/records/"
    "legacy_seeded_plan_authority_mpi8_v1.json"
)
TASK035D_T30_AUTHORITY_FILE_SHA256 = (
    "97e8ddaab151cfc985c43c66256c036f3809ee216c47f67710a1f01679de0961"
)
TASK035D_T30_PLAN_CONTENT_SHA256 = (
    "862a0347792c356858b405d27f9874cfb9a28b3d75034d73f75c594c5c43c26d"
)
TASK035D_T30_GEOMETRY_CATALOG_SHA256 = (
    "e33ae0611cfe3d9d380ec04af0b86efec7f7f751cdb2dd90a9bd936d71dbcf64"
)
TASK035D_T30_SEED_GEOMETRY_SHA256 = (
    "b68a588e99032c9972740621bf01f15807d92d6025919bb097a53e92e75852a7"
)
TASK035D_T30_SEED_PAYLOAD_SHA256 = (
    "b3420dbdfce689cfa14e9b87e51910943d81b160dbd8a4b9e3c5798526f4b68c"
)
TASK035D_T30_RECORD_SHA256 = (
    "ac0266578fe38dd9934cfcfb840d817f8c4fbc617694a068462f7d505392acc1"
)
TASK035D_T30_CELL_DEGREE_COUNTS = {"p4": 144, "p5": 56, "p6": 52}
TASK035D_T30_ACTIVE_FE_DOFS = 87_600
TASK035D_T30_ACTIVE_TRACE_ROWS = 35_208
TASK035D_T30_PERIODIC_TRACE_ROWS = 28_910
TASK035D_T30_DTN_ROWS = 80
TASK035D_T30_SOLVE_ROWS = 28_990
TASK035D_SIDEWALL_GUARD_PLAN_NAME = "sidewall_z0_guard_v1"
TASK035D_SIDEWALL_GUARD_PLAN_PATH = (
    "benchmarks/cases/"
    "097_goal_oriented_exact_sequence_hp_adaptivity/records/"
    "sidewall_z0_guard_h10_cell_degree_plan_v1.json"
)
TASK035D_SIDEWALL_GUARD_PLAN_FILE_SHA256 = (
    "31922411775580b2f44b474897dbf877d96b7887f74d22e02b3f0e410c205bc2"
)
TASK035D_SIDEWALL_GUARD_AUTHORITY_PATH = (
    "benchmarks/cases/"
    "097_goal_oriented_exact_sequence_hp_adaptivity/records/"
    "physics_guard_plan_authority_mpi8_v1.json"
)
TASK035D_SIDEWALL_GUARD_AUTHORITY_FILE_SHA256 = (
    "ccf40707125425540bd60a8118fed4fd74f9138968624255eb1e4fa25c8e911d"
)
TASK035D_SIDEWALL_GUARD_DIAGNOSTIC_PATH = (
    "benchmarks/cases/"
    "097_goal_oriented_exact_sequence_hp_adaptivity/records/"
    "t30_regional_probe_error_localization_v1.json"
)
TASK035D_SIDEWALL_GUARD_DIAGNOSTIC_SHA256 = (
    "baaca8a90a98d459e392468778528edc43217d1c6fa19969592044522d498f3f"
)
TASK035D_SIDEWALL_GUARD_AUTHORITY_SOURCE_SHA = (
    "c6fa966333b722dddcd76ac91227f5415cef8147"
)
TASK035D_SIDEWALL_GUARD_PLAN_CONTENT_SHA256 = (
    "8172bcc9ca2e2fcbc23a8ca15524f80b7658ccf0c19d24da4dcff1ed32fee062"
)
TASK035D_SIDEWALL_GUARD_CELL_DEGREE_COUNTS = {
    "p4": 72,
    "p5": 168,
    "p6": 12,
}
TASK035D_SIDEWALL_GUARD_CYCLE1_COUNTS = {
    "p4": 0,
    "p5": 240,
    "p6": 12,
}
TASK035D_SIDEWALL_GUARD_ACTIVE_FE_DOFS = 89_870
TASK035D_SIDEWALL_GUARD_ACTIVE_TRACE_ROWS = 36_374
TASK035D_SIDEWALL_GUARD_PERIODIC_TRACE_ROWS = 30_984
TASK035D_SIDEWALL_GUARD_DTN_ROWS = 80
TASK035D_SIDEWALL_GUARD_SOLVE_ROWS = 31_064
TASK035D_SIDEWALL_GUARD_ROW_BREAKDOWN = {
    "edge": 4_902,
    "face": 31_472,
    "cell_interior": 53_496,
}
TASK035D_H10_MESH_SHA256 = (
    "f0eef2aa28e86014b661a921993bcfd45e6db1892da350402f2be11ec64dd857"
)
TASK035D_H10_CELL_TAG_SHA256 = (
    "42f511fc7ffddcbc2972d641018e16a845f48c11067ccd9a9686695ad5cfc131"
)
TASK035D_H10_FACET_TAG_SHA256 = (
    "0adbcfed35e1840460f826cb1ca1695ed87c0c3960e2073377d2f50871c3c0bd"
)
TASK035D_LOCAL_H_PLAN_NAME = "h15_top_air_local_h_v1"
TASK035D_LOCAL_H_PLAN_PATH = (
    "benchmarks/cases/"
    "097_goal_oriented_exact_sequence_hp_adaptivity/records/"
    "h15_top_air_local_h_plan_v1.json"
)
TASK035D_LOCAL_H_PLAN_FILE_SHA256 = (
    "c4d8a5bd3cb16735f9027c21e531b720517180ee5f2d510042f6ed23dad112a1"
)
TASK035D_LOCAL_H_AUTHORITY_PATH = (
    "benchmarks/cases/"
    "097_goal_oriented_exact_sequence_hp_adaptivity/records/"
    "local_h_production_mpi_identity_v3_owner_gate_fix2.json"
)
TASK035D_LOCAL_H_AUTHORITY_FILE_SHA256 = (
    "358d52097a4eff4cf78b2b02d3a19d0e553f13e3ec7f7ddcda6e6ad1b55504f9"
)
TASK035D_LOCAL_H_COMPONENT_SOURCE_SHA = (
    "571b65fe5f9832a421bd2354969d7f06680ec7bf"
)
TASK035D_LOCAL_H_CHECKER_SOURCE_SHA = (
    "4fe95dbef3436277fba631371e8ed3a1f0baa684"
)
TASK035D_LOCAL_H_BASE_CONFIG_SHA256 = (
    "a99e7aaf2eb7f100356ae9ef2b5ec83575ddd68095c742d9a91954b37cfd54a7"
)
TASK035D_LOCAL_H_LEAF_CATALOG_SHA256 = (
    "1ad308302e1d20bdf14ba2177b8c94d787cba09b722cb02a197b32c646031943"
)
TASK035D_LOCAL_H_HANGING_CATALOG_SHA256 = (
    "8b70b5c1d679eceb638ff9c3c55ef8c8cf18e007ba939a84b1b39334902d0712"
)
TASK035D_LOCAL_H_CARRIER_SHA256 = (
    "b94b6a85a439ce5170e9e628e88e60adb22b91fc43590a8f7f753cbfc20f9aec"
)
TASK035D_LOCAL_H_PHYSICAL_FACET_SHA256 = (
    "41b250c6629025e82a674c2d9a67bd1d0e60857c6b77a9dbfca98f3d138a5f97"
)
TASK035D_LOCAL_H_MATERIAL_SHA256 = (
    "806a2a9ed3e63a9a5df4d0b981df6a9ef52c5466ed64a48671ab2917389bef6e"
)
TASK035D_LOCAL_H_PHYSICAL_AUTHORITY_SHA256 = (
    "877f3088424d47ea4debc9ef23cd70abd2c5b3f8e4424ce20718e7a7b4772fac"
)
TASK035D_LOCAL_H_FLATTENED_GRAPH_SHA256 = (
    "7677482e10d5b159ce20344b566bc2704bbd5ad4a7cb5ac375d3c51826fa582d"
)
TASK035D_LOCAL_H_CELL_GRAPH_SHA256 = (
    "8af31327df6760ad3f1ebbe0ecbf21af65ad656f7bcf78dea9c02f96c8995211"
)
TASK035D_LOCAL_H_BOX_CATALOG_SHA256 = (
    "de8f9293edacfdfe30f5972c36347121add8c88203912330b0ab8e9d71d88c20"
)
TASK035D_LOCAL_H_ROOT_CELLS = 120
TASK035D_LOCAL_H_LEAF_CELLS = 134
TASK035D_LOCAL_H_HANGING_PATCHES = 6
TASK035D_LOCAL_H_RAW_ACTIVE_FE_DOFS = 84_175
TASK035D_LOCAL_H_RAW_TRACE_ROWS = 23_875
TASK035D_LOCAL_H_HANGING_SLAVE_ROWS = 1_250
TASK035D_LOCAL_H_PERIODIC_SLAVE_ROWS = 4_235
TASK035D_LOCAL_H_ACTIVE_FE_DOFS = 82_925
TASK035D_LOCAL_H_INDEPENDENT_TRACE_ROWS = 18_390
TASK035D_LOCAL_H_DTN_ROWS = 80
TASK035D_LOCAL_H_SOLVE_ROWS = 18_470
TASK035D_COMBINED_HP_PLAN_NAME = (
    "h15_symmetric_top_air_remote_p5_interior_v1"
)
TASK035D_COMBINED_HP_PLAN_PATH = (
    "benchmarks/cases/"
    "097_goal_oriented_exact_sequence_hp_adaptivity/records/"
    "h15_symmetric_top_air_remote_p5_interior_plan_v1.json"
)
TASK035D_COMBINED_HP_PLAN_FILE_SHA256 = (
    "1d0b1ef0d6cfb28f463efb0df70d3b4c864e26fbeaeeb413e28e71689f5de520"
)
TASK035D_COMBINED_HP_AUTHORITY_PATH = (
    "benchmarks/cases/"
    "097_goal_oriented_exact_sequence_hp_adaptivity/records/"
    "combined_hp_interior_mpi_identity_v2.json"
)
TASK035D_COMBINED_HP_AUTHORITY_FILE_SHA256 = (
    "f978cc3430b3cb6e8445f5aa268590fd8c03214153456a1a0cb14f409351bdd7"
)
TASK035D_COMBINED_HP_COMPONENT_SOURCE_SHA = (
    "459dea914b2508cd9a22f4348bdcba85351272d0"
)
TASK035D_COMBINED_HP_CHECKER_SOURCE_SHA = (
    "459dea914b2508cd9a22f4348bdcba85351272d0"
)
TASK035D_COMBINED_HP_LEAF_CATALOG_SHA256 = (
    "4b1df873d791e4716a0744b36aa524d0a9e5c842aba9395516c9d8792f93f846"
)
TASK035D_COMBINED_HP_HANGING_CATALOG_SHA256 = (
    "2f7c6c4bcb6c7d71a71c78ac2dab1caddc2914b01b041949b7371b68f309bd27"
)
TASK035D_COMBINED_HP_CARRIER_SHA256 = (
    "13a15c1b4e77ad23fbe308fa98fee7f34d0867bec2a6dea2136cc5ebb973c76f"
)
TASK035D_COMBINED_HP_PHYSICAL_FACET_SHA256 = (
    "c3f9ac50081be93ae6a1402f922953339065af8586e045b6810a25a777c80191"
)
TASK035D_COMBINED_HP_MATERIAL_SHA256 = (
    "c79dc64620f2a13ed88e1cb0e6fb4e7757c74583bdd7f8d7be01ab9548034f6f"
)
TASK035D_COMBINED_HP_PHYSICAL_AUTHORITY_SHA256 = (
    "1315a11c31da9aebfb5c04489feb4d96f16c4749d9891691b8d16bd9cfab06dc"
)
TASK035D_COMBINED_HP_FLATTENED_GRAPH_SHA256 = (
    "097b07aa5657270a5b5dce00752c1e9353bf75fdccc16b8ffa78f290f41eb8a3"
)
TASK035D_COMBINED_HP_CELL_GRAPH_SHA256 = (
    "691bf41fb9c2df3d93cbb079c0251830bdc462709ba06e9d30bd42117515ce87"
)
TASK035D_COMBINED_HP_BOX_CATALOG_SHA256 = (
    "c2a50a595f06166d2ee5c52b8bf5ab327ccd5155015b046d905fe9b9ace2d681"
)
TASK035D_COMBINED_HP_CELL_DEGREE_PLAN_SHA256 = (
    "c78634f2cb0cf6b0a1ca417d483e25b74cc2f28b54fa3e78af139731a300b7cf"
)
TASK035D_COMBINED_HP_ENTITY_DEGREE_SHA256 = (
    "61d3dfcea2854a3fc543537301e07ce9dd173820bb6665a96bfcba753cfe4ff7"
)
TASK035D_COMBINED_HP_ROOT_CELLS = 120
TASK035D_COMBINED_HP_LEAF_CELLS = 148
TASK035D_COMBINED_HP_HANGING_PATCHES = 12
TASK035D_COMBINED_HP_RAW_ACTIVE_FE_DOFS = 86_740
TASK035D_COMBINED_HP_RAW_TRACE_ROWS = 26_860
TASK035D_COMBINED_HP_HANGING_SLAVE_ROWS = 2_500
TASK035D_COMBINED_HP_PERIODIC_SLAVE_ROWS = 4_380
TASK035D_COMBINED_HP_ACTIVE_FE_DOFS = 84_240
TASK035D_COMBINED_HP_INDEPENDENT_TRACE_ROWS = 19_980
TASK035D_COMBINED_HP_DTN_ROWS = 80
TASK035D_COMBINED_HP_SOLVE_ROWS = 20_060
TASK035D_COMBINED_HP_CELL_DEGREE_COUNTS = {
    "p4": 0,
    "p5": 32,
    "p6": 116,
}
TASK035D_HP_FACTORIAL_BRIDGE_PLAN_NAME = (
    "h15_top_air_remote_p5_interior_bridge_v1"
)
TASK035D_HP_FACTORIAL_BRIDGE_PLAN_PATH = (
    "benchmarks/cases/"
    "097_goal_oriented_exact_sequence_hp_adaptivity/records/"
    "h15_top_air_remote_p5_interior_bridge_plan_v1.json"
)
TASK035D_HP_FACTORIAL_BRIDGE_PLAN_FILE_SHA256 = (
    "6775a173939175af0a84e3941276c2d2fe8116353b8ee609fd1dbfa61f3c1859"
)
TASK035D_HP_FACTORIAL_BRIDGE_AUTHORITY_PATH = (
    "benchmarks/cases/"
    "097_goal_oriented_exact_sequence_hp_adaptivity/records/"
    "hp_factorial_bridge_mpi_identity_v1.json"
)
TASK035D_HP_FACTORIAL_BRIDGE_AUTHORITY_FILE_SHA256 = (
    "5914f01c13eb031b9a8075734c0e1718a1bfa7b339eb9abba9cfc40584cf5f59"
)
TASK035D_HP_FACTORIAL_BRIDGE_COMPONENT_SOURCE_SHA = (
    "289ca9a85d407efc8d6382a081ae13d6925e29a6"
)
TASK035D_HP_FACTORIAL_BRIDGE_CHECKER_SOURCE_SHA = (
    "289ca9a85d407efc8d6382a081ae13d6925e29a6"
)
TASK035D_HP_FACTORIAL_BRIDGE_CELL_DEGREE_PLAN_SHA256 = (
    "ab62c9e369125424068d04edc170172064aed5e63da02fdc741b27664bd7adb6"
)
TASK035D_HP_FACTORIAL_BRIDGE_ENTITY_DEGREE_SHA256 = (
    "d17a503fa0d28bbd91e94087df5a4bfa7309fe65ab49263c295b66fd37af9f8a"
)
TASK035D_HP_FACTORIAL_BRIDGE_RAW_ACTIVE_FE_DOFS = 77_455
TASK035D_HP_FACTORIAL_BRIDGE_RAW_TRACE_ROWS = 23_875
TASK035D_HP_FACTORIAL_BRIDGE_ACTIVE_FE_DOFS = 76_205
TASK035D_HP_FACTORIAL_BRIDGE_INDEPENDENT_TRACE_ROWS = 18_390
TASK035D_HP_FACTORIAL_BRIDGE_DTN_ROWS = 80
TASK035D_HP_FACTORIAL_BRIDGE_SOLVE_ROWS = 18_470
TASK035D_HP_FACTORIAL_BRIDGE_CELL_DEGREE_COUNTS = {
    "p4": 0,
    "p5": 32,
    "p6": 102,
}

_COMBINED_HP_GATE_SPEC = {
    "candidate_name": TASK035D_COMBINED_HP_PLAN_NAME,
    "plan_path": TASK035D_COMBINED_HP_PLAN_PATH,
    "plan_file_sha256": TASK035D_COMBINED_HP_PLAN_FILE_SHA256,
    "authority_path": TASK035D_COMBINED_HP_AUTHORITY_PATH,
    "authority_file_sha256": TASK035D_COMBINED_HP_AUTHORITY_FILE_SHA256,
    "component_source_sha": TASK035D_COMBINED_HP_COMPONENT_SOURCE_SHA,
    "checker_source_sha": TASK035D_COMBINED_HP_CHECKER_SOURCE_SHA,
    "leaf_catalog_sha256": TASK035D_COMBINED_HP_LEAF_CATALOG_SHA256,
    "hanging_catalog_sha256": (
        TASK035D_COMBINED_HP_HANGING_CATALOG_SHA256
    ),
    "carrier_sha256": TASK035D_COMBINED_HP_CARRIER_SHA256,
    "physical_facet_sha256": TASK035D_COMBINED_HP_PHYSICAL_FACET_SHA256,
    "material_sha256": TASK035D_COMBINED_HP_MATERIAL_SHA256,
    "physical_authority_sha256": (
        TASK035D_COMBINED_HP_PHYSICAL_AUTHORITY_SHA256
    ),
    "flattened_graph_sha256": (
        TASK035D_COMBINED_HP_FLATTENED_GRAPH_SHA256
    ),
    "cell_graph_sha256": TASK035D_COMBINED_HP_CELL_GRAPH_SHA256,
    "box_catalog_sha256": TASK035D_COMBINED_HP_BOX_CATALOG_SHA256,
    "cell_degree_plan_sha256": (
        TASK035D_COMBINED_HP_CELL_DEGREE_PLAN_SHA256
    ),
    "entity_degree_sha256": TASK035D_COMBINED_HP_ENTITY_DEGREE_SHA256,
    "root_cells": TASK035D_COMBINED_HP_ROOT_CELLS,
    "leaf_cells": TASK035D_COMBINED_HP_LEAF_CELLS,
    "hanging_patches": TASK035D_COMBINED_HP_HANGING_PATCHES,
    "raw_active_fe_dofs": TASK035D_COMBINED_HP_RAW_ACTIVE_FE_DOFS,
    "raw_trace_rows": TASK035D_COMBINED_HP_RAW_TRACE_ROWS,
    "hanging_slave_rows": TASK035D_COMBINED_HP_HANGING_SLAVE_ROWS,
    "periodic_slave_rows": TASK035D_COMBINED_HP_PERIODIC_SLAVE_ROWS,
    "active_fe_dofs": TASK035D_COMBINED_HP_ACTIVE_FE_DOFS,
    "independent_trace_rows": (
        TASK035D_COMBINED_HP_INDEPENDENT_TRACE_ROWS
    ),
    "dtn_rows": TASK035D_COMBINED_HP_DTN_ROWS,
    "solve_rows": TASK035D_COMBINED_HP_SOLVE_ROWS,
    "cell_degree_counts": TASK035D_COMBINED_HP_CELL_DEGREE_COUNTS,
    "marked_root_boxes": [
        {
            "lower": [8.25, 0.0, 120.0],
            "upper": [16.5, 12.5, 130.0],
        },
        {
            "lower": [33.5, 0.0, 120.0],
            "upper": [41.75, 12.5, 130.0],
        },
    ],
    "closure_counts": {
        "balance": 0,
        "material": 0,
        "periodic": 2,
        "user": 2,
    },
    "authority_schema": "case097.combined-hp-interior-mpi-identity.v2",
    "authority_status": "combined_hp_interior_mpi_identity_pass",
    "launch_schema": (
        "task035d.case097-combined-hp-interior-launch-gate.v1"
    ),
    "launch_pass_status": (
        "task035d_combined_hp_interior_launch_authority_pass"
    ),
    "launch_fail_status": (
        "task035d_combined_hp_interior_launch_authority_fail"
    ),
    "solver_schema": (
        "task035d.case097-combined-hp-interior-solver-gate.v1"
    ),
    "solver_pass_status": (
        "task035d_combined_hp_interior_solver_identity_pass"
    ),
    "solver_fail_status": (
        "task035d_combined_hp_interior_solver_identity_fail"
    ),
    "selection_credit": {
        "structural_resource_anchor": True,
        "actual_channel_dwr": False,
        "goal_oriented_selection_credit": False,
        "complete_combined_hp_credit": False,
    },
    "expected_inputs": [
        {
            "mpi_size": 1,
            "path": (
                "benchmarks/cases/"
                "097_goal_oriented_exact_sequence_hp_adaptivity/records/"
                "combined_hp_interior_mpi1_v2.json"
            ),
            "sha256": (
                "6f13691de05b9471b51fbab0865c713f4d49f7a03b27a082df2ae4c2f2b41d9e"
            ),
        },
        {
            "mpi_size": 2,
            "path": (
                "benchmarks/cases/"
                "097_goal_oriented_exact_sequence_hp_adaptivity/records/"
                "combined_hp_interior_mpi2_v2.json"
            ),
            "sha256": (
                "e5d6272a2ee7ec45e86b8aa06defd6d7d81bcb93ca9c7ae2b3c0add9d6235093"
            ),
        },
        {
            "mpi_size": 8,
            "path": (
                "benchmarks/cases/"
                "097_goal_oriented_exact_sequence_hp_adaptivity/records/"
                "combined_hp_interior_mpi8_v2.json"
            ),
            "sha256": (
                "012353dc18da1a91b13963d88d6b98826c0614db10b9aae7152a95cdc2cf29b4"
            ),
        },
    ],
}

_HP_FACTORIAL_BRIDGE_GATE_SPEC = {
    **_COMBINED_HP_GATE_SPEC,
    "candidate_name": TASK035D_HP_FACTORIAL_BRIDGE_PLAN_NAME,
    "plan_path": TASK035D_HP_FACTORIAL_BRIDGE_PLAN_PATH,
    "plan_file_sha256": TASK035D_HP_FACTORIAL_BRIDGE_PLAN_FILE_SHA256,
    "authority_path": TASK035D_HP_FACTORIAL_BRIDGE_AUTHORITY_PATH,
    "authority_file_sha256": (
        TASK035D_HP_FACTORIAL_BRIDGE_AUTHORITY_FILE_SHA256
    ),
    "component_source_sha": (
        TASK035D_HP_FACTORIAL_BRIDGE_COMPONENT_SOURCE_SHA
    ),
    "checker_source_sha": TASK035D_HP_FACTORIAL_BRIDGE_CHECKER_SOURCE_SHA,
    "leaf_catalog_sha256": TASK035D_LOCAL_H_LEAF_CATALOG_SHA256,
    "hanging_catalog_sha256": TASK035D_LOCAL_H_HANGING_CATALOG_SHA256,
    "carrier_sha256": TASK035D_LOCAL_H_CARRIER_SHA256,
    "physical_facet_sha256": TASK035D_LOCAL_H_PHYSICAL_FACET_SHA256,
    "material_sha256": TASK035D_LOCAL_H_MATERIAL_SHA256,
    "physical_authority_sha256": (
        TASK035D_LOCAL_H_PHYSICAL_AUTHORITY_SHA256
    ),
    "flattened_graph_sha256": TASK035D_LOCAL_H_FLATTENED_GRAPH_SHA256,
    "cell_graph_sha256": TASK035D_LOCAL_H_CELL_GRAPH_SHA256,
    "box_catalog_sha256": TASK035D_LOCAL_H_BOX_CATALOG_SHA256,
    "cell_degree_plan_sha256": (
        TASK035D_HP_FACTORIAL_BRIDGE_CELL_DEGREE_PLAN_SHA256
    ),
    "entity_degree_sha256": TASK035D_HP_FACTORIAL_BRIDGE_ENTITY_DEGREE_SHA256,
    "root_cells": TASK035D_LOCAL_H_ROOT_CELLS,
    "leaf_cells": TASK035D_LOCAL_H_LEAF_CELLS,
    "hanging_patches": TASK035D_LOCAL_H_HANGING_PATCHES,
    "raw_active_fe_dofs": TASK035D_HP_FACTORIAL_BRIDGE_RAW_ACTIVE_FE_DOFS,
    "raw_trace_rows": TASK035D_HP_FACTORIAL_BRIDGE_RAW_TRACE_ROWS,
    "hanging_slave_rows": TASK035D_LOCAL_H_HANGING_SLAVE_ROWS,
    "periodic_slave_rows": TASK035D_LOCAL_H_PERIODIC_SLAVE_ROWS,
    "active_fe_dofs": TASK035D_HP_FACTORIAL_BRIDGE_ACTIVE_FE_DOFS,
    "independent_trace_rows": (
        TASK035D_HP_FACTORIAL_BRIDGE_INDEPENDENT_TRACE_ROWS
    ),
    "dtn_rows": TASK035D_HP_FACTORIAL_BRIDGE_DTN_ROWS,
    "solve_rows": TASK035D_HP_FACTORIAL_BRIDGE_SOLVE_ROWS,
    "cell_degree_counts": TASK035D_HP_FACTORIAL_BRIDGE_CELL_DEGREE_COUNTS,
    "marked_root_boxes": [
        {
            "lower": [8.25, 0.0, 120.0],
            "upper": [16.5, 12.5, 130.0],
        },
    ],
    "closure_counts": {
        "balance": 0,
        "material": 0,
        "periodic": 1,
        "user": 1,
    },
    "authority_schema": "case097.hp-factorial-bridge-mpi-identity.v1",
    "authority_status": "hp_factorial_bridge_mpi_identity_pass",
    "launch_schema": (
        "task035d.case097-hp-factorial-bridge-launch-gate.v1"
    ),
    "launch_pass_status": (
        "task035d_hp_factorial_bridge_launch_authority_pass"
    ),
    "launch_fail_status": (
        "task035d_hp_factorial_bridge_launch_authority_fail"
    ),
    "solver_schema": (
        "task035d.case097-hp-factorial-bridge-solver-gate.v1"
    ),
    "solver_pass_status": (
        "task035d_hp_factorial_bridge_solver_identity_pass"
    ),
    "solver_fail_status": (
        "task035d_hp_factorial_bridge_solver_identity_fail"
    ),
    "selection_credit": {
        "structural_resource_anchor": True,
        "factorial_bridge_credit": True,
        "actual_channel_dwr": False,
        "goal_oriented_selection_credit": False,
        "complete_combined_hp_credit": False,
    },
    "expected_inputs": [
        {
            "mpi_size": 1,
            "path": (
                "benchmarks/cases/"
                "097_goal_oriented_exact_sequence_hp_adaptivity/records/"
                "hp_factorial_bridge_mpi1_v1.json"
            ),
            "sha256": (
                "b3c0bbaa4eaae9506c1b89456c54f69605d5d93f0d31279ee9d052d72025bf9f"
            ),
        },
        {
            "mpi_size": 2,
            "path": (
                "benchmarks/cases/"
                "097_goal_oriented_exact_sequence_hp_adaptivity/records/"
                "hp_factorial_bridge_mpi2_v1.json"
            ),
            "sha256": (
                "d5bd3e71f09fb714cff627cc465ca56762e250b27b5debf874e850b7edf74934"
            ),
        },
        {
            "mpi_size": 8,
            "path": (
                "benchmarks/cases/"
                "097_goal_oriented_exact_sequence_hp_adaptivity/records/"
                "hp_factorial_bridge_mpi8_v1.json"
            ),
            "sha256": (
                "0620be15b293c65b3440ef2504bf830cdc63a657910a1c664d0d90a036196cc1"
            ),
        },
    ],
}


def _valid_hex(value: Any, length: int) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == length
        and all(character in "0123456789abcdef" for character in value.lower())
    )


def _t30_authority_entry(authority: dict[str, Any]) -> dict[str, Any]:
    plans = authority.get("plans")
    if not isinstance(plans, list):
        return {}
    matches = [
        plan
        for plan in plans
        if isinstance(plan, dict)
        and plan.get("name") == TASK035D_T30_PLAN_NAME
    ]
    return matches[0] if len(matches) == 1 else {}


def task035d_case097_plan_authority_gate(
    plan: dict[str, Any] | None,
    authority: dict[str, Any] | None,
    *,
    expected_plan_file_sha256: str | None,
    observed_plan_file_sha256: str | None,
    expected_authority_sha256: str | None,
    observed_authority_sha256: str | None,
    plan_is_tracked: bool,
    authority_is_tracked: bool,
    plan_path_from_root: str | None,
    authority_path_from_root: str | None,
) -> dict[str, Any]:
    """Validate the tracked MPI8 T30 launch authority without accuracy credit."""

    plan = plan if isinstance(plan, dict) else {}
    authority = authority if isinstance(authority, dict) else {}
    closure = plan.get("closure_audit")
    closure = closure if isinstance(closure, dict) else {}
    provenance = plan.get("provenance")
    provenance = provenance if isinstance(provenance, dict) else {}
    selector = provenance.get("selector_audit")
    selector = selector if isinstance(selector, dict) else {}
    periodic = selector.get("periodic_constraint_audit")
    periodic = periodic if isinstance(periodic, dict) else {}
    periodic_checks = periodic.get("checks")
    periodic_checks = (
        periodic_checks if isinstance(periodic_checks, dict) else {}
    )
    seed = selector.get("seed_audit")
    seed = seed if isinstance(seed, dict) else {}
    authority_entry = _t30_authority_entry(authority)
    environment = authority.get("environment")
    environment = environment if isinstance(environment, dict) else {}
    cells = plan.get("cells")
    cell_degrees = (
        Counter(int(row.get("degree", -1)) for row in cells)
        if isinstance(cells, list)
        and all(isinstance(row, dict) for row in cells)
        else Counter()
    )
    observed_degree_counts = {
        f"p{degree}": int(cell_degrees[degree])
        for degree in (4, 5, 6)
    }

    checks = {
        "plan_is_tracked": plan_is_tracked,
        "authority_is_tracked": authority_is_tracked,
        "plan_expected_sha_is_valid": _valid_hex(
            expected_plan_file_sha256,
            64,
        ),
        "authority_expected_sha_is_valid": _valid_hex(
            expected_authority_sha256,
            64,
        ),
        "plan_file_hash_matches_expected": (
            observed_plan_file_sha256 == expected_plan_file_sha256
        ),
        "plan_file_hash_matches_frozen_t30": (
            observed_plan_file_sha256 == TASK035D_T30_PLAN_FILE_SHA256
            and expected_plan_file_sha256 == TASK035D_T30_PLAN_FILE_SHA256
        ),
        "authority_file_hash_matches_expected": (
            observed_authority_sha256 == expected_authority_sha256
        ),
        "authority_file_hash_matches_frozen_mpi8": (
            observed_authority_sha256
            == TASK035D_T30_AUTHORITY_FILE_SHA256
            and expected_authority_sha256
            == TASK035D_T30_AUTHORITY_FILE_SHA256
        ),
        "plan_schema": (
            plan.get("schema_version") == TASK035D_CASE097_PLAN_SCHEMA
        ),
        "plan_status": plan.get("status") == "geometry_bound_cell_degree_plan",
        "plan_path_identity": plan_path_from_root == TASK035D_T30_PLAN_PATH,
        "authority_path_identity": (
            authority_path_from_root == TASK035D_T30_AUTHORITY_PATH
        ),
        "plan_content_sha": (
            plan.get("cell_degree_plan_sha256")
            == TASK035D_T30_PLAN_CONTENT_SHA256
        ),
        "plan_geometry_catalog_sha": (
            plan.get("mesh_cell_box_catalog_sha256")
            == TASK035D_T30_GEOMETRY_CATALOG_SHA256
        ),
        "plan_cell_count": isinstance(cells, list) and len(cells) == 252,
        "plan_cell_degree_counts": (
            observed_degree_counts == TASK035D_T30_CELL_DEGREE_COUNTS
        ),
        "plan_closure_pass": closure.get("pass") is True,
        "plan_active_fe_dofs": (
            closure.get("active_rows") == TASK035D_T30_ACTIVE_FE_DOFS
        ),
        "plan_active_trace_rows": (
            closure.get("active_trace_rows")
            == TASK035D_T30_ACTIVE_TRACE_ROWS
        ),
        "plan_inactive_rows_absent": (
            closure.get("inactive_p6_rows") == 86_202
            and closure.get("inactive_p6_trace_rows") == 25_194
        ),
        "plan_adjacent_degree_jump": (
            closure.get("maximum_adjacent_cell_degree_jump") == 1
        ),
        "plan_ordinary_default_unchanged": (
            plan.get("ordinary_default_changed") is False
            and closure.get("ordinary_default_changed") is False
            and provenance.get("ordinary_default_changed") is False
        ),
        "historical_seed_is_not_accuracy_authority": (
            provenance.get("formal_accuracy_credit") is False
            and provenance.get("fresh_12_channel_pde_required") is True
            and selector.get("historical_seed_only") is True
            and seed.get("production_qualified") is False
        ),
        "seed_payload_identity": (
            provenance.get("seed_payload_sha256")
            == TASK035D_T30_SEED_PAYLOAD_SHA256
            and seed.get("payload_sha256")
            == TASK035D_T30_SEED_PAYLOAD_SHA256
            and seed.get("mesh_geometry_sha256")
            == TASK035D_T30_SEED_GEOMETRY_SHA256
        ),
        "selector_pass": selector.get("pass") is True,
        "selector_active_fe_gate": (
            selector.get("actual_conforming_active_fe_dofs")
            == TASK035D_T30_ACTIVE_FE_DOFS
            and selector.get("active_fe_dof_gate_pass") is True
        ),
        "selector_periodic_trace_rows": (
            selector.get("periodic_independent_trace_rows")
            == TASK035D_T30_PERIODIC_TRACE_ROWS
        ),
        "selector_solve_rows": (
            selector.get("predicted_direct_solve_rows")
            == TASK035D_T30_SOLVE_ROWS
            and selector.get("appended_dtn_rows") == TASK035D_T30_DTN_ROWS
        ),
        "periodic_constraint_pass": (
            periodic.get("pass") is True
            and periodic.get("independent_periodic_trace_rows")
            == TASK035D_T30_PERIODIC_TRACE_ROWS
            and periodic_checks.get(
                "slave_rows_eliminated_before_insertion"
            )
            is True
            and periodic.get("inactive_p6_rows_globally_numbered") is False
        ),
        "authority_schema": (
            authority.get("schema_version")
            == TASK035D_CASE097_AUTHORITY_SCHEMA
        ),
        "authority_status": (
            authority.get("status")
            == "legacy_seeded_plan_authority_mpi8_pass"
            and authority.get("pass") is True
        ),
        "authority_environment": (
            environment.get("mpi_size") == 8
            and environment.get("petsc_scalar_type") == "complex128"
            and environment.get("petsc_int_type") == "int32"
        ),
        "authority_fixed_case": (
            authority.get("actual_axis_counts") == [6, 3, 14]
            and authority.get("cell_count") == 252
            and authority.get("degree_container") == 6
            and authority.get("h_nm") == 10.0
            and authority.get("geometry")
            == "Task034 fixed rectangular block grating"
        ),
        "authority_is_pre_pde_only": (
            authority.get("formal_accuracy_credit") is False
            and authority.get("fresh_12_channel_pde_required") is True
            and authority.get("seed_production_qualified") is False
            and authority.get("heavy_pde_started") is False
        ),
        "authority_entry_plan_path": (
            authority_entry.get("plan_file") == TASK035D_T30_PLAN_PATH
        ),
        "authority_entry_file_hash": (
            authority_entry.get("plan_file_sha256")
            == observed_plan_file_sha256
        ),
        "authority_entry_plan_content": (
            authority_entry.get("cell_degree_plan_sha256")
            == TASK035D_T30_PLAN_CONTENT_SHA256
            and authority_entry.get("cell_degree_counts")
            == TASK035D_T30_CELL_DEGREE_COUNTS
        ),
        "authority_entry_dimensions": (
            authority_entry.get("actual_conforming_active_fe_dofs")
            == TASK035D_T30_ACTIVE_FE_DOFS
            and authority_entry.get("periodic_independent_trace_rows")
            == TASK035D_T30_PERIODIC_TRACE_ROWS
            and authority_entry.get("predicted_direct_solve_rows")
            == TASK035D_T30_SOLVE_ROWS
        ),
        "authority_ordinary_default_unchanged": (
            authority.get("ordinary_default_changed") is False
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": "task035d.case097-t30-launch-gate.v1",
        "status": (
            "task035d_t30_launch_authority_pass"
            if not failures
            else "task035d_t30_launch_authority_fail"
        ),
        "pass": not failures,
        "checks": checks,
        "failures": failures,
        "plan_identity": {
            "name": TASK035D_T30_PLAN_NAME,
            "path": plan_path_from_root,
            "file_sha256": observed_plan_file_sha256,
            "cell_degree_plan_sha256": plan.get(
                "cell_degree_plan_sha256"
            ),
            "mesh_cell_box_catalog_sha256": plan.get(
                "mesh_cell_box_catalog_sha256"
            ),
            "cell_degree_counts": observed_degree_counts,
            "actual_conforming_active_fe_dofs": closure.get("active_rows"),
            "periodic_independent_trace_rows": selector.get(
                "periodic_independent_trace_rows"
            ),
            "predicted_direct_solve_rows": selector.get(
                "predicted_direct_solve_rows"
            ),
        },
        "accuracy_credit": (
            "none_until_fresh_12_channel_checker_passes"
        ),
        "ordinary_default_changed": False,
    }


def task035d_case097_sidewall_guard_plan_authority_gate(
    plan: dict[str, Any] | None,
    authority: dict[str, Any] | None,
    *,
    expected_plan_file_sha256: str | None,
    observed_plan_file_sha256: str | None,
    expected_authority_sha256: str | None,
    observed_authority_sha256: str | None,
    plan_is_tracked: bool,
    authority_is_tracked: bool,
    plan_path_from_root: str | None,
    authority_path_from_root: str | None,
) -> dict[str, Any]:
    """Validate the tracked MPI8 sidewall-z0 recovery launch authority."""

    plan = plan if isinstance(plan, dict) else {}
    authority = authority if isinstance(authority, dict) else {}
    closure = plan.get("closure_audit")
    closure = closure if isinstance(closure, dict) else {}
    provenance = plan.get("provenance")
    provenance = provenance if isinstance(provenance, dict) else {}
    selector = provenance.get("selector_audit")
    selector = selector if isinstance(selector, dict) else {}
    periodic = selector.get("periodic_constraint_audit")
    periodic = periodic if isinstance(periodic, dict) else {}
    periodic_checks = periodic.get("checks")
    periodic_checks = (
        periodic_checks if isinstance(periodic_checks, dict) else {}
    )
    diagnostic = provenance.get("regional_diagnostic")
    diagnostic = diagnostic if isinstance(diagnostic, dict) else {}
    authority_diagnostic = authority.get("regional_diagnostic")
    authority_diagnostic = (
        authority_diagnostic
        if isinstance(authority_diagnostic, dict)
        else {}
    )
    authority_plan = authority.get("plan")
    authority_plan = (
        authority_plan if isinstance(authority_plan, dict) else {}
    )
    environment = authority.get("environment")
    environment = environment if isinstance(environment, dict) else {}
    source = authority.get("source")
    source = source if isinstance(source, dict) else {}
    cells = plan.get("cells")
    cell_degrees = (
        Counter(int(row.get("degree", -1)) for row in cells)
        if isinstance(cells, list)
        and all(isinstance(row, dict) for row in cells)
        else Counter()
    )
    observed_degree_counts = {
        f"p{degree}": int(cell_degrees[degree])
        for degree in (4, 5, 6)
    }
    checks = {
        "plan_is_tracked": plan_is_tracked,
        "authority_is_tracked": authority_is_tracked,
        "plan_expected_sha_is_valid": _valid_hex(
            expected_plan_file_sha256,
            64,
        ),
        "authority_expected_sha_is_valid": _valid_hex(
            expected_authority_sha256,
            64,
        ),
        "plan_file_hash_matches_expected": (
            observed_plan_file_sha256 == expected_plan_file_sha256
        ),
        "plan_file_hash_matches_frozen_sidewall_guard": (
            observed_plan_file_sha256
            == TASK035D_SIDEWALL_GUARD_PLAN_FILE_SHA256
            and expected_plan_file_sha256
            == TASK035D_SIDEWALL_GUARD_PLAN_FILE_SHA256
        ),
        "authority_file_hash_matches_expected": (
            observed_authority_sha256 == expected_authority_sha256
        ),
        "authority_file_hash_matches_frozen_mpi8": (
            observed_authority_sha256
            == TASK035D_SIDEWALL_GUARD_AUTHORITY_FILE_SHA256
            and expected_authority_sha256
            == TASK035D_SIDEWALL_GUARD_AUTHORITY_FILE_SHA256
        ),
        "plan_schema": (
            plan.get("schema_version") == TASK035D_CASE097_PLAN_SCHEMA
        ),
        "plan_status": plan.get("status") == "geometry_bound_cell_degree_plan",
        "plan_path_identity": (
            plan_path_from_root == TASK035D_SIDEWALL_GUARD_PLAN_PATH
        ),
        "authority_path_identity": (
            authority_path_from_root
            == TASK035D_SIDEWALL_GUARD_AUTHORITY_PATH
        ),
        "plan_content_sha": (
            plan.get("cell_degree_plan_sha256")
            == TASK035D_SIDEWALL_GUARD_PLAN_CONTENT_SHA256
        ),
        "plan_geometry_catalog_sha": (
            plan.get("mesh_cell_box_catalog_sha256")
            == TASK035D_T30_GEOMETRY_CATALOG_SHA256
        ),
        "plan_cell_count": isinstance(cells, list) and len(cells) == 252,
        "plan_cell_degree_counts": (
            observed_degree_counts
            == TASK035D_SIDEWALL_GUARD_CELL_DEGREE_COUNTS
        ),
        "plan_closure_pass": closure.get("pass") is True,
        "plan_active_fe_dofs": (
            closure.get("active_rows")
            == TASK035D_SIDEWALL_GUARD_ACTIVE_FE_DOFS
        ),
        "plan_active_trace_rows": (
            closure.get("active_trace_rows")
            == TASK035D_SIDEWALL_GUARD_ACTIVE_TRACE_ROWS
        ),
        "plan_inactive_rows_absent": (
            closure.get("inactive_p6_rows") == 83_932
            and closure.get("inactive_p6_trace_rows") == 24_028
        ),
        "plan_adjacent_degree_jump": (
            closure.get("maximum_adjacent_cell_degree_jump") == 1
        ),
        "plan_ordinary_default_unchanged": (
            plan.get("ordinary_default_changed") is False
            and closure.get("ordinary_default_changed") is False
            and provenance.get("ordinary_default_changed") is False
        ),
        "selector_identity": (
            provenance.get("selector")
            == TASK035D_SIDEWALL_GUARD_PLAN_NAME
            and selector.get("selector")
            == TASK035D_SIDEWALL_GUARD_PLAN_NAME
            and selector.get("status")
            == "sidewall_z0_guard_two_cycle_plan_pass"
            and selector.get("pass") is True
        ),
        "selector_is_diagnostic_not_dwr": (
            selector.get("diagnostic_only_selector") is True
            and selector.get("actual_channel_dwr") is False
            and selector.get("formal_accuracy_credit") is False
            and provenance.get("formal_accuracy_credit") is False
            and provenance.get("fresh_12_channel_pde_required") is True
        ),
        "diagnostic_identity": (
            diagnostic.get("path")
            == TASK035D_SIDEWALL_GUARD_DIAGNOSTIC_PATH
            and diagnostic.get("sha256")
            == TASK035D_SIDEWALL_GUARD_DIAGNOSTIC_SHA256
            and provenance.get("t30_compact_record_sha256")
            == TASK035D_T30_RECORD_SHA256
        ),
        "selector_dimensions": (
            selector.get("cycle1_cell_degree_counts")
            == TASK035D_SIDEWALL_GUARD_CYCLE1_COUNTS
            and selector.get("cell_degree_counts")
            == TASK035D_SIDEWALL_GUARD_CELL_DEGREE_COUNTS
            and selector.get("actual_conforming_active_fe_dofs")
            == TASK035D_SIDEWALL_GUARD_ACTIVE_FE_DOFS
            and selector.get(
                "active_trace_rows_before_periodic_elimination"
            )
            == TASK035D_SIDEWALL_GUARD_ACTIVE_TRACE_ROWS
            and selector.get("active_rows_by_dimension")
            == TASK035D_SIDEWALL_GUARD_ROW_BREAKDOWN
            and selector.get("active_fe_dof_gate_pass") is True
        ),
        "selector_periodic_trace_rows": (
            selector.get("periodic_independent_trace_rows")
            == TASK035D_SIDEWALL_GUARD_PERIODIC_TRACE_ROWS
            and selector.get("predicted_direct_solve_rows")
            == TASK035D_SIDEWALL_GUARD_SOLVE_ROWS
            and selector.get("appended_dtn_rows")
            == TASK035D_SIDEWALL_GUARD_DTN_ROWS
        ),
        "periodic_constraint_pass": (
            periodic.get("pass") is True
            and periodic.get("independent_periodic_trace_rows")
            == TASK035D_SIDEWALL_GUARD_PERIODIC_TRACE_ROWS
            and periodic_checks.get(
                "slave_rows_eliminated_before_insertion"
            )
            is True
            and periodic.get("inactive_p6_rows_globally_numbered") is False
        ),
        "authority_schema": (
            authority.get("schema_version")
            == "task035d.physics-guard-plan-authority.v1"
        ),
        "authority_status": (
            authority.get("status")
            == "physics_guard_plan_authority_mpi8_pass"
            and authority.get("pass") is True
        ),
        "authority_source": (
            source.get("commit_sha")
            == TASK035D_SIDEWALL_GUARD_AUTHORITY_SOURCE_SHA
            and isinstance(source.get("file_sha256"), dict)
            and bool(source.get("file_sha256"))
            and all(
                _valid_hex(value, 64)
                for value in source["file_sha256"].values()
            )
        ),
        "authority_environment": (
            environment.get("mpi_size") == 8
            and environment.get("petsc_scalar_type") == "complex128"
            and environment.get("petsc_int_type") == "int32"
        ),
        "authority_fixed_case": (
            authority.get("actual_axis_counts") == [6, 3, 14]
            and authority.get("cell_count") == 252
            and authority.get("degree_container") == 6
            and authority.get("h_nm") == 10.0
            and authority.get("geometry")
            == "Task034 fixed rectangular block grating"
            and authority.get("candidate")
            == TASK035D_SIDEWALL_GUARD_PLAN_NAME
        ),
        "authority_is_pre_pde_only": (
            authority.get("formal_accuracy_credit") is False
            and authority.get("fresh_12_channel_pde_required") is True
            and authority.get("heavy_pde_started") is False
        ),
        "authority_diagnostic_identity": (
            authority_diagnostic.get("path")
            == TASK035D_SIDEWALL_GUARD_DIAGNOSTIC_PATH
            and authority_diagnostic.get("sha256")
            == TASK035D_SIDEWALL_GUARD_DIAGNOSTIC_SHA256
            and authority_diagnostic.get("diagnostic_only") is True
            and authority_diagnostic.get("actual_channel_dwr") is False
            and authority_diagnostic.get("formal_accuracy_credit") is False
        ),
        "authority_plan_identity": (
            authority_plan.get("path")
            == TASK035D_SIDEWALL_GUARD_PLAN_PATH
            and authority_plan.get("file_sha256")
            == TASK035D_SIDEWALL_GUARD_PLAN_FILE_SHA256
            and authority_plan.get("cell_degree_plan_sha256")
            == TASK035D_SIDEWALL_GUARD_PLAN_CONTENT_SHA256
            and authority_plan.get("cell_degree_counts")
            == TASK035D_SIDEWALL_GUARD_CELL_DEGREE_COUNTS
            and authority_plan.get("cycle1_cell_degree_counts")
            == TASK035D_SIDEWALL_GUARD_CYCLE1_COUNTS
            and authority_plan.get("actual_conforming_active_fe_dofs")
            == TASK035D_SIDEWALL_GUARD_ACTIVE_FE_DOFS
            and authority_plan.get(
                "active_trace_rows_before_periodic_elimination"
            )
            == TASK035D_SIDEWALL_GUARD_ACTIVE_TRACE_ROWS
            and authority_plan.get("periodic_independent_trace_rows")
            == TASK035D_SIDEWALL_GUARD_PERIODIC_TRACE_ROWS
            and authority_plan.get("predicted_direct_solve_rows")
            == TASK035D_SIDEWALL_GUARD_SOLVE_ROWS
            and authority_plan.get("active_rows_by_dimension")
            == TASK035D_SIDEWALL_GUARD_ROW_BREAKDOWN
            and authority_plan.get("maximum_adjacent_cell_degree_jump") == 1
            and authority_plan.get("active_fe_dof_gate_pass") is True
        ),
        "authority_ordinary_default_unchanged": (
            authority.get("ordinary_default_changed") is False
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": (
            "task035d.case097-sidewall-z0-guard-launch-gate.v1"
        ),
        "status": (
            "task035d_sidewall_z0_guard_launch_authority_pass"
            if not failures
            else "task035d_sidewall_z0_guard_launch_authority_fail"
        ),
        "pass": not failures,
        "checks": checks,
        "failures": failures,
        "plan_identity": {
            "name": TASK035D_SIDEWALL_GUARD_PLAN_NAME,
            "path": plan_path_from_root,
            "file_sha256": observed_plan_file_sha256,
            "cell_degree_plan_sha256": plan.get(
                "cell_degree_plan_sha256"
            ),
            "mesh_cell_box_catalog_sha256": plan.get(
                "mesh_cell_box_catalog_sha256"
            ),
            "cell_degree_counts": observed_degree_counts,
            "actual_conforming_active_fe_dofs": closure.get("active_rows"),
            "periodic_independent_trace_rows": selector.get(
                "periodic_independent_trace_rows"
            ),
            "predicted_direct_solve_rows": selector.get(
                "predicted_direct_solve_rows"
            ),
        },
        "accuracy_credit": (
            "none_until_fresh_12_channel_checker_passes"
        ),
        "ordinary_default_changed": False,
    }


def task035d_case097_local_h_plan_authority_gate(
    plan: dict[str, Any] | None,
    authority: dict[str, Any] | None,
    *,
    expected_plan_file_sha256: str | None,
    observed_plan_file_sha256: str | None,
    expected_authority_sha256: str | None,
    observed_authority_sha256: str | None,
    plan_is_tracked: bool,
    authority_is_tracked: bool,
    plan_path_from_root: str | None,
    authority_path_from_root: str | None,
) -> dict[str, Any]:
    """Validate the first tracked h15 production local-h launch authority."""

    plan = plan if isinstance(plan, dict) else {}
    authority = authority if isinstance(authority, dict) else {}
    base = plan.get("base_config")
    base = base if isinstance(base, dict) else {}
    forest = plan.get("expected_forest")
    forest = forest if isinstance(forest, dict) else {}
    provenance = plan.get("provenance")
    provenance = provenance if isinstance(provenance, dict) else {}
    stable = authority.get("stable_identity")
    stable = stable if isinstance(stable, dict) else {}
    cross = authority.get("cross_checks")
    cross = cross if isinstance(cross, dict) else {}
    checker = authority.get("checker_identity")
    checker = checker if isinstance(checker, dict) else {}
    expected_stable = {
        "actual_full3d_equivalent_active_fe_dofs": (
            TASK035D_LOCAL_H_ACTIVE_FE_DOFS
        ),
        "base_config_identity_sha256": (
            TASK035D_LOCAL_H_BASE_CONFIG_SHA256
        ),
        "canonical_cell_graph_sha256": (
            TASK035D_LOCAL_H_CELL_GRAPH_SHA256
        ),
        "carrier_connectivity_sha256": (
            TASK035D_LOCAL_H_CARRIER_SHA256
        ),
        "flattened_graph_sha256": (
            TASK035D_LOCAL_H_FLATTENED_GRAPH_SHA256
        ),
        "hanging_face_catalog_sha256": (
            TASK035D_LOCAL_H_HANGING_CATALOG_SHA256
        ),
        "hanging_patch_count": TASK035D_LOCAL_H_HANGING_PATCHES,
        "hanging_slave_rows": TASK035D_LOCAL_H_HANGING_SLAVE_ROWS,
        "independent_trace_rows": (
            TASK035D_LOCAL_H_INDEPENDENT_TRACE_ROWS
        ),
        "leaf_catalog_sha256": TASK035D_LOCAL_H_LEAF_CATALOG_SHA256,
        "leaf_cell_count": TASK035D_LOCAL_H_LEAF_CELLS,
        "material_catalog_sha256": TASK035D_LOCAL_H_MATERIAL_SHA256,
        "mesh_cell_box_catalog_sha256": (
            TASK035D_LOCAL_H_BOX_CATALOG_SHA256
        ),
        "periodic_slave_rows": TASK035D_LOCAL_H_PERIODIC_SLAVE_ROWS,
        "physical_authority_sha256": (
            TASK035D_LOCAL_H_PHYSICAL_AUTHORITY_SHA256
        ),
        "physical_facet_catalog_sha256": (
            TASK035D_LOCAL_H_PHYSICAL_FACET_SHA256
        ),
        "plan_file_sha256": TASK035D_LOCAL_H_PLAN_FILE_SHA256,
        "predicted_direct_solve_rows": TASK035D_LOCAL_H_SOLVE_ROWS,
        "raw_broken_active_fe_dofs": (
            TASK035D_LOCAL_H_RAW_ACTIVE_FE_DOFS
        ),
        "raw_broken_trace_rows": TASK035D_LOCAL_H_RAW_TRACE_ROWS,
        "root_cell_count": TASK035D_LOCAL_H_ROOT_CELLS,
    }
    expected_inputs = [
        {
            "mpi_size": 1,
            "path": (
                "benchmarks/cases/"
                "097_goal_oriented_exact_sequence_hp_adaptivity/records/"
                "local_h_production_mpi1_v3_owner_gate_fix1.json"
            ),
            "sha256": (
                "511654d93451b9fedc6de49b75a688428b59a57a07a07832155ba5bfc4e42f86"
            ),
        },
        {
            "mpi_size": 2,
            "path": (
                "benchmarks/cases/"
                "097_goal_oriented_exact_sequence_hp_adaptivity/records/"
                "local_h_production_mpi2_v3_owner_gate_fix1.json"
            ),
            "sha256": (
                "218d50bcd5abbb12a57f15fc343f8cca8c209a3065dd1eee5a1b5d9871c841fa"
            ),
        },
        {
            "mpi_size": 8,
            "path": (
                "benchmarks/cases/"
                "097_goal_oriented_exact_sequence_hp_adaptivity/records/"
                "local_h_production_mpi8_v3_owner_gate_fix1.json"
            ),
            "sha256": (
                "5038ef247d48302b67fb04600f17894dbef0331d974a073bd5b924c29ea8f676"
            ),
        },
    ]
    checks = {
        "plan_is_tracked": plan_is_tracked,
        "authority_is_tracked": authority_is_tracked,
        "plan_expected_sha_is_valid": _valid_hex(
            expected_plan_file_sha256,
            64,
        ),
        "authority_expected_sha_is_valid": _valid_hex(
            expected_authority_sha256,
            64,
        ),
        "plan_file_hash_matches_frozen": (
            observed_plan_file_sha256
            == expected_plan_file_sha256
            == TASK035D_LOCAL_H_PLAN_FILE_SHA256
        ),
        "authority_file_hash_matches_frozen": (
            observed_authority_sha256
            == expected_authority_sha256
            == TASK035D_LOCAL_H_AUTHORITY_FILE_SHA256
        ),
        "path_identity": (
            plan_path_from_root == TASK035D_LOCAL_H_PLAN_PATH
            and authority_path_from_root
            == TASK035D_LOCAL_H_AUTHORITY_PATH
        ),
        "plan_schema_and_status": (
            plan.get("schema_version")
            == "task035d.stage4-local-h-refinement-plan.v1"
            and plan.get("status") == "stage4_balanced_local_h_plan"
        ),
        "fixed_h15_geometry": (
            base.get("identity_sha256")
            == TASK035D_LOCAL_H_BASE_CONFIG_SHA256
            and base.get("stage_case") == "stage4_block_grating"
            and base.get("geometry_kind") == "rectangular_block_grating"
            and base.get("mesh_target_size") == 15.0
            and base.get("mesh_cells_resolved") == [6, 2, 10]
            and base.get("period_x") == 50.0
            and base.get("period_y") == 25.0
        ),
        "one_balanced_periodic_split": (
            plan.get("periodic_axes") == ["x", "y"]
            and plan.get("protect_material_interfaces") is True
            and plan.get("maximum_level") == 1
            and plan.get("marked_root_boxes")
            == [
                {
                    "lower": [8.25, 0.0, 120.0],
                    "upper": [16.5, 12.5, 130.0],
                }
            ]
            and forest.get("closure_counts")
            == {"balance": 0, "material": 0, "periodic": 1, "user": 1}
        ),
        "p5_trace_p6_interior": (
            plan.get("trace_degree") == 5
            and plan.get("cell_interior_degree") == 6
        ),
        "forest_identity": (
            forest.get("root_cell_count") == TASK035D_LOCAL_H_ROOT_CELLS
            and forest.get("leaf_cell_count") == TASK035D_LOCAL_H_LEAF_CELLS
            and forest.get("hanging_patch_count")
            == TASK035D_LOCAL_H_HANGING_PATCHES
            and forest.get("leaf_catalog_sha256")
            == TASK035D_LOCAL_H_LEAF_CATALOG_SHA256
            and forest.get("hanging_face_catalog_sha256")
            == TASK035D_LOCAL_H_HANGING_CATALOG_SHA256
        ),
        "selection_credit_is_structural_only": (
            provenance.get("candidate_id") == TASK035D_LOCAL_H_PLAN_NAME
            and provenance.get("accuracy_credit") is False
            and "minimum top-air local-h split"
            in str(provenance.get("seed", ""))
        ),
        "ordinary_default_unchanged": (
            plan.get("ordinary_default_changed") is False
            and provenance.get("ordinary_default_changed") is False
            and authority.get("ordinary_default_changed") is False
        ),
        "authority_schema_and_status": (
            authority.get("schema_version")
            == "case097.local-h-production-mpi-identity.v3-integration"
            and authority.get("status")
            == "local_h_production_mpi_identity_pass"
            and authority.get("pass") is True
            and authority.get("candidate_id")
            == TASK035D_LOCAL_H_PLAN_NAME
        ),
        "authority_component_source": (
            authority.get("source_sha")
            == TASK035D_LOCAL_H_COMPONENT_SOURCE_SHA
            and _valid_hex(authority.get("source_sha"), 40)
        ),
        "authority_checker_source": (
            authority.get("live_head")
            == TASK035D_LOCAL_H_CHECKER_SOURCE_SHA
            and checker.get("source_sha")
            == TASK035D_LOCAL_H_CHECKER_SOURCE_SHA
            and checker.get("verified_clean_checker") is True
            and checker.get("status_lines") == []
        ),
        "authority_inputs": authority.get("input_records") == expected_inputs,
        "authority_cross_checks": (
            bool(cross) and all(value is True for value in cross.values())
        ),
        "authority_stable_identity": stable == expected_stable,
        "authority_plan_identity": (
            authority.get("plan")
            == {
                "path": TASK035D_LOCAL_H_PLAN_PATH,
                "sha256": TASK035D_LOCAL_H_PLAN_FILE_SHA256,
            }
        ),
        "authority_is_pre_pde_only": (
            authority.get("pde_launch_gate") is True
            and authority.get("pde_accuracy_credit") is False
            and authority.get("failures") == []
        ),
        "active_fe_dof_gate": (
            stable.get("actual_full3d_equivalent_active_fe_dofs")
            == TASK035D_LOCAL_H_ACTIVE_FE_DOFS
            and TASK035D_LOCAL_H_ACTIVE_FE_DOFS <= 90_000
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": "task035d.case097-h15-local-h-launch-gate.v1",
        "status": (
            "task035d_h15_local_h_launch_authority_pass"
            if not failures
            else "task035d_h15_local_h_launch_authority_fail"
        ),
        "pass": not failures,
        "checks": checks,
        "failures": failures,
        "plan_identity": {
            "name": TASK035D_LOCAL_H_PLAN_NAME,
            "path": plan_path_from_root,
            "file_sha256": observed_plan_file_sha256,
            "base_config_identity_sha256": base.get("identity_sha256"),
            "leaf_catalog_sha256": forest.get("leaf_catalog_sha256"),
            "actual_conforming_active_fe_dofs": (
                TASK035D_LOCAL_H_ACTIVE_FE_DOFS
            ),
            "raw_broken_active_fe_dofs": (
                TASK035D_LOCAL_H_RAW_ACTIVE_FE_DOFS
            ),
            "periodic_independent_trace_rows": (
                TASK035D_LOCAL_H_INDEPENDENT_TRACE_ROWS
            ),
            "predicted_direct_solve_rows": TASK035D_LOCAL_H_SOLVE_ROWS,
        },
        "selection_credit": {
            "structural_resource_anchor": True,
            "actual_channel_dwr": False,
            "goal_oriented_selection_credit": False,
        },
        "accuracy_credit": (
            "none_until_fresh_12_channel_checker_passes"
        ),
        "ordinary_default_changed": False,
    }


def _task035d_case097_variable_interior_plan_authority_gate(
    plan: dict[str, Any] | None,
    authority: dict[str, Any] | None,
    *,
    expected_plan_file_sha256: str | None,
    observed_plan_file_sha256: str | None,
    expected_authority_sha256: str | None,
    observed_authority_sha256: str | None,
    plan_is_tracked: bool,
    authority_is_tracked: bool,
    plan_path_from_root: str | None,
    authority_path_from_root: str | None,
    spec: dict[str, Any],
) -> dict[str, Any]:
    """Validate one fixed-trace local-h/variable-interior launch."""

    TASK035D_COMBINED_HP_PLAN_NAME = spec["candidate_name"]
    TASK035D_COMBINED_HP_PLAN_PATH = spec["plan_path"]
    TASK035D_COMBINED_HP_PLAN_FILE_SHA256 = spec["plan_file_sha256"]
    TASK035D_COMBINED_HP_AUTHORITY_PATH = spec["authority_path"]
    TASK035D_COMBINED_HP_AUTHORITY_FILE_SHA256 = spec[
        "authority_file_sha256"
    ]
    TASK035D_COMBINED_HP_COMPONENT_SOURCE_SHA = spec[
        "component_source_sha"
    ]
    TASK035D_COMBINED_HP_CHECKER_SOURCE_SHA = spec["checker_source_sha"]
    TASK035D_COMBINED_HP_LEAF_CATALOG_SHA256 = spec[
        "leaf_catalog_sha256"
    ]
    TASK035D_COMBINED_HP_HANGING_CATALOG_SHA256 = spec[
        "hanging_catalog_sha256"
    ]
    TASK035D_COMBINED_HP_CARRIER_SHA256 = spec["carrier_sha256"]
    TASK035D_COMBINED_HP_PHYSICAL_FACET_SHA256 = spec[
        "physical_facet_sha256"
    ]
    TASK035D_COMBINED_HP_MATERIAL_SHA256 = spec["material_sha256"]
    TASK035D_COMBINED_HP_PHYSICAL_AUTHORITY_SHA256 = spec[
        "physical_authority_sha256"
    ]
    TASK035D_COMBINED_HP_FLATTENED_GRAPH_SHA256 = spec[
        "flattened_graph_sha256"
    ]
    TASK035D_COMBINED_HP_CELL_GRAPH_SHA256 = spec["cell_graph_sha256"]
    TASK035D_COMBINED_HP_BOX_CATALOG_SHA256 = spec[
        "box_catalog_sha256"
    ]
    TASK035D_COMBINED_HP_CELL_DEGREE_PLAN_SHA256 = spec[
        "cell_degree_plan_sha256"
    ]
    TASK035D_COMBINED_HP_ENTITY_DEGREE_SHA256 = spec[
        "entity_degree_sha256"
    ]
    TASK035D_COMBINED_HP_ROOT_CELLS = spec["root_cells"]
    TASK035D_COMBINED_HP_LEAF_CELLS = spec["leaf_cells"]
    TASK035D_COMBINED_HP_HANGING_PATCHES = spec["hanging_patches"]
    TASK035D_COMBINED_HP_RAW_ACTIVE_FE_DOFS = spec["raw_active_fe_dofs"]
    TASK035D_COMBINED_HP_RAW_TRACE_ROWS = spec["raw_trace_rows"]
    TASK035D_COMBINED_HP_HANGING_SLAVE_ROWS = spec[
        "hanging_slave_rows"
    ]
    TASK035D_COMBINED_HP_PERIODIC_SLAVE_ROWS = spec[
        "periodic_slave_rows"
    ]
    TASK035D_COMBINED_HP_ACTIVE_FE_DOFS = spec["active_fe_dofs"]
    TASK035D_COMBINED_HP_INDEPENDENT_TRACE_ROWS = spec[
        "independent_trace_rows"
    ]
    TASK035D_COMBINED_HP_SOLVE_ROWS = spec["solve_rows"]
    TASK035D_COMBINED_HP_CELL_DEGREE_COUNTS = spec[
        "cell_degree_counts"
    ]

    plan = plan if isinstance(plan, dict) else {}
    authority = authority if isinstance(authority, dict) else {}
    base = plan.get("base_config")
    base = base if isinstance(base, dict) else {}
    forest = plan.get("expected_forest")
    forest = forest if isinstance(forest, dict) else {}
    provenance = plan.get("provenance")
    provenance = provenance if isinstance(provenance, dict) else {}
    degree_rows = plan.get("cell_interior_degrees")
    degree_rows = degree_rows if isinstance(degree_rows, list) else []
    stable = authority.get("stable_identity")
    stable = stable if isinstance(stable, dict) else {}
    cross = authority.get("cross_checks")
    cross = cross if isinstance(cross, dict) else {}
    checker = authority.get("checker_identity")
    checker = checker if isinstance(checker, dict) else {}
    expected_stable = {
        "actual_full3d_equivalent_active_fe_dofs": (
            TASK035D_COMBINED_HP_ACTIVE_FE_DOFS
        ),
        "base_config_identity_sha256": (
            TASK035D_LOCAL_H_BASE_CONFIG_SHA256
        ),
        "canonical_cell_graph_sha256": (
            TASK035D_COMBINED_HP_CELL_GRAPH_SHA256
        ),
        "carrier_connectivity_sha256": (
            TASK035D_COMBINED_HP_CARRIER_SHA256
        ),
        "cell_degree_counts": TASK035D_COMBINED_HP_CELL_DEGREE_COUNTS,
        "cell_degree_plan_sha256": (
            TASK035D_COMBINED_HP_CELL_DEGREE_PLAN_SHA256
        ),
        "flattened_graph_sha256": (
            TASK035D_COMBINED_HP_FLATTENED_GRAPH_SHA256
        ),
        "geometry_canonical_entity_degree_sha256": (
            TASK035D_COMBINED_HP_ENTITY_DEGREE_SHA256
        ),
        "hanging_face_catalog_sha256": (
            TASK035D_COMBINED_HP_HANGING_CATALOG_SHA256
        ),
        "hanging_patch_count": TASK035D_COMBINED_HP_HANGING_PATCHES,
        "hanging_slave_rows": TASK035D_COMBINED_HP_HANGING_SLAVE_ROWS,
        "independent_trace_rows": (
            TASK035D_COMBINED_HP_INDEPENDENT_TRACE_ROWS
        ),
        "leaf_catalog_sha256": (
            TASK035D_COMBINED_HP_LEAF_CATALOG_SHA256
        ),
        "leaf_cell_count": TASK035D_COMBINED_HP_LEAF_CELLS,
        "material_catalog_sha256": TASK035D_COMBINED_HP_MATERIAL_SHA256,
        "mesh_cell_box_catalog_sha256": (
            TASK035D_COMBINED_HP_BOX_CATALOG_SHA256
        ),
        "periodic_slave_rows": TASK035D_COMBINED_HP_PERIODIC_SLAVE_ROWS,
        "physical_authority_sha256": (
            TASK035D_COMBINED_HP_PHYSICAL_AUTHORITY_SHA256
        ),
        "physical_facet_catalog_sha256": (
            TASK035D_COMBINED_HP_PHYSICAL_FACET_SHA256
        ),
        "plan_file_sha256": TASK035D_COMBINED_HP_PLAN_FILE_SHA256,
        "predicted_direct_solve_rows": TASK035D_COMBINED_HP_SOLVE_ROWS,
        "raw_broken_active_fe_dofs": (
            TASK035D_COMBINED_HP_RAW_ACTIVE_FE_DOFS
        ),
        "raw_broken_trace_rows": TASK035D_COMBINED_HP_RAW_TRACE_ROWS,
        "root_cell_count": TASK035D_COMBINED_HP_ROOT_CELLS,
    }
    expected_inputs = list(spec["expected_inputs"])
    degree_counts = Counter(
        int(row.get("degree", -1))
        for row in degree_rows
        if isinstance(row, dict)
    )
    checks = {
        "plan_and_authority_tracked": plan_is_tracked and authority_is_tracked,
        "expected_hashes_valid": (
            _valid_hex(expected_plan_file_sha256, 64)
            and _valid_hex(expected_authority_sha256, 64)
        ),
        "frozen_file_hashes": (
            observed_plan_file_sha256
            == expected_plan_file_sha256
            == TASK035D_COMBINED_HP_PLAN_FILE_SHA256
            and observed_authority_sha256
            == expected_authority_sha256
            == TASK035D_COMBINED_HP_AUTHORITY_FILE_SHA256
        ),
        "path_identity": (
            plan_path_from_root == TASK035D_COMBINED_HP_PLAN_PATH
            and authority_path_from_root
            == TASK035D_COMBINED_HP_AUTHORITY_PATH
        ),
        "plan_schema_and_h15_identity": (
            plan.get("schema_version")
            == "task035d.stage4-local-h-refinement-plan.v1"
            and plan.get("status") == "stage4_balanced_local_h_plan"
            and base.get("identity_sha256")
            == TASK035D_LOCAL_H_BASE_CONFIG_SHA256
            and base.get("stage_case") == "stage4_block_grating"
            and base.get("geometry_kind") == "rectangular_block_grating"
            and base.get("mesh_target_size") == 15.0
            and base.get("mesh_cells_resolved") == [6, 2, 10]
        ),
        "balanced_periodic_h_action": (
            plan.get("periodic_axes") == ["x", "y"]
            and plan.get("protect_material_interfaces") is True
            and plan.get("maximum_level") == 1
            and plan.get("marked_root_boxes") == spec["marked_root_boxes"]
            and forest.get("closure_counts") == spec["closure_counts"]
        ),
        "true_p5_p6_variable_interiors": (
            plan.get("trace_degree") == 5
            and plan.get("cell_interior_degree") == 6
            and len(degree_rows) == TASK035D_COMBINED_HP_LEAF_CELLS
            and degree_counts
            == Counter(
                {
                    int(key.removeprefix("p")): int(value)
                    for key, value in spec["cell_degree_counts"].items()
                    if int(value) > 0
                }
            )
            and plan.get("cell_interior_degree_plan_sha256")
            == TASK035D_COMBINED_HP_CELL_DEGREE_PLAN_SHA256
        ),
        "forest_identity": (
            forest.get("root_cell_count") == TASK035D_COMBINED_HP_ROOT_CELLS
            and forest.get("leaf_cell_count")
            == TASK035D_COMBINED_HP_LEAF_CELLS
            and forest.get("hanging_patch_count")
            == TASK035D_COMBINED_HP_HANGING_PATCHES
            and forest.get("leaf_catalog_sha256")
            == TASK035D_COMBINED_HP_LEAF_CATALOG_SHA256
            and forest.get("hanging_face_catalog_sha256")
            == TASK035D_COMBINED_HP_HANGING_CATALOG_SHA256
        ),
        "selection_credit_is_limited": (
            provenance.get("candidate_id")
            == TASK035D_COMBINED_HP_PLAN_NAME
            and provenance.get("accuracy_credit") is False
            and provenance.get("complete_combined_hp_credit") is False
            and "not actual DWR" in str(
                provenance.get("h_action_evidence", "")
            )
            and "no variable trace" in str(
                provenance.get("p_action_evidence", "")
            )
        ),
        "ordinary_default_unchanged": (
            plan.get("ordinary_default_changed") is False
            and provenance.get("ordinary_default_changed") is False
            and authority.get("ordinary_default_changed") is False
        ),
        "authority_identity": (
            authority.get("schema_version") == spec["authority_schema"]
            and authority.get("status") == spec["authority_status"]
            and authority.get("pass") is True
            and authority.get("candidate_id")
            == TASK035D_COMBINED_HP_PLAN_NAME
            and authority.get("source_sha")
            == TASK035D_COMBINED_HP_COMPONENT_SOURCE_SHA
            and authority.get("live_head")
            == TASK035D_COMBINED_HP_CHECKER_SOURCE_SHA
            and checker.get("source_sha")
            == TASK035D_COMBINED_HP_CHECKER_SOURCE_SHA
            and checker.get("verified_clean_checker") is True
            and checker.get("status_lines") == []
        ),
        "authority_inputs_and_cross_checks": (
            authority.get("input_records") == expected_inputs
            and bool(cross)
            and all(value is True for value in cross.values())
        ),
        "authority_stable_identity": stable == expected_stable,
        "authority_plan_identity": (
            authority.get("plan")
            == {
                "path": TASK035D_COMBINED_HP_PLAN_PATH,
                "sha256": TASK035D_COMBINED_HP_PLAN_FILE_SHA256,
            }
        ),
        "authority_is_pre_pde_only": (
            authority.get("pde_launch_gate") is True
            and authority.get("pde_accuracy_credit") is False
            and authority.get("failures") == []
        ),
        "active_fe_dof_gate": (
            stable.get("actual_full3d_equivalent_active_fe_dofs")
            == TASK035D_COMBINED_HP_ACTIVE_FE_DOFS
            and TASK035D_COMBINED_HP_ACTIVE_FE_DOFS <= 90_000
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": spec["launch_schema"],
        "status": (
            spec["launch_pass_status"]
            if not failures
            else spec["launch_fail_status"]
        ),
        "pass": not failures,
        "checks": checks,
        "failures": failures,
        "plan_identity": {
            "name": TASK035D_COMBINED_HP_PLAN_NAME,
            "path": plan_path_from_root,
            "file_sha256": observed_plan_file_sha256,
            "base_config_identity_sha256": base.get("identity_sha256"),
            "leaf_catalog_sha256": forest.get("leaf_catalog_sha256"),
            "actual_conforming_active_fe_dofs": (
                TASK035D_COMBINED_HP_ACTIVE_FE_DOFS
            ),
            "raw_broken_active_fe_dofs": (
                TASK035D_COMBINED_HP_RAW_ACTIVE_FE_DOFS
            ),
            "periodic_independent_trace_rows": (
                TASK035D_COMBINED_HP_INDEPENDENT_TRACE_ROWS
            ),
            "predicted_direct_solve_rows": TASK035D_COMBINED_HP_SOLVE_ROWS,
        },
        "selection_credit": dict(spec["selection_credit"]),
        "accuracy_credit": (
            "none_until_fresh_12_channel_checker_passes"
        ),
        "ordinary_default_changed": False,
    }


def task035d_case097_combined_hp_plan_authority_gate(
    plan: dict[str, Any] | None,
    authority: dict[str, Any] | None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Validate the symmetric fixed-trace h/interior-p launch."""

    return _task035d_case097_variable_interior_plan_authority_gate(
        plan,
        authority,
        spec=_COMBINED_HP_GATE_SPEC,
        **kwargs,
    )


def task035d_case097_hp_factorial_bridge_plan_authority_gate(
    plan: dict[str, Any] | None,
    authority: dict[str, Any] | None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Validate the one-sided-h/remote-interior-p factorial bridge."""

    return _task035d_case097_variable_interior_plan_authority_gate(
        plan,
        authority,
        spec=_HP_FACTORIAL_BRIDGE_GATE_SPEC,
        **kwargs,
    )


def _task035d_case097_solver_gate(
    solver_summary: dict[str, Any] | None,
    *,
    candidate_name: str,
    active_fe_dofs: int,
    active_trace_rows: int,
    periodic_trace_rows: int,
    solve_rows: int,
    dtn_rows: int,
    plan_content_sha256: str,
    cell_degree_counts: dict[str, int],
    schema_version: str,
    pass_status: str,
    fail_status: str,
) -> dict[str, Any]:
    """Check the exact variable-p reduction identity before physics comparison."""

    summary = solver_summary if isinstance(solver_summary, dict) else {}
    matrix = summary.get("matrix_stats")
    matrix = matrix if isinstance(matrix, dict) else {}
    config = summary.get("config")
    config = config if isinstance(config, dict) else {}
    audit = summary.get("cell_static_condensation")
    audit = audit if isinstance(audit, dict) else {}
    degree_plan = audit.get("degree_plan")
    degree_plan = degree_plan if isinstance(degree_plan, dict) else {}
    periodic = audit.get("periodic_constraints")
    periodic = periodic if isinstance(periodic, dict) else {}
    recovery = audit.get("recovery")
    recovery = recovery if isinstance(recovery, dict) else {}
    full_residual = audit.get("full_explicit_true_residual")
    full_residual = (
        full_residual if isinstance(full_residual, dict) else {}
    )
    backend_qualification = summary.get(
        "stage4_full3d_assembly_backend_qualification"
    )
    backend_audit = summary.get("stage4_full3d_assembly_backend_audit")
    backend_audit = (
        backend_audit if isinstance(backend_audit, dict) else {}
    )
    backend_qualification = (
        backend_qualification
        if isinstance(backend_qualification, dict)
        else {}
    )
    factor_inventory = summary.get("stage4_dtn_factor_inventory")
    factor_inventory = (
        factor_inventory if isinstance(factor_inventory, dict) else {}
    )
    factor_matrix = factor_inventory.get("matrix_stats")
    factor_matrix = (
        factor_matrix if isinstance(factor_matrix, dict) else {}
    )
    solver_release = summary.get("solver_release_audit")
    solver_release = (
        solver_release if isinstance(solver_release, dict) else {}
    )
    heap_trim = solver_release.get("process_heap_trim")
    heap_trim = heap_trim if isinstance(heap_trim, dict) else {}
    global_transfer = audit.get("global_transfer")
    global_transfer = (
        global_transfer if isinstance(global_transfer, dict) else {}
    )
    condensed_system = audit.get("condensed_system")
    condensed_system = (
        condensed_system if isinstance(condensed_system, dict) else {}
    )
    mesh_identity = summary.get("variable_p_mesh_identity")
    mesh_identity = (
        mesh_identity if isinstance(mesh_identity, dict) else {}
    )
    orientation = summary.get("nedelec_orientation_factor_stats")
    orientation = orientation if isinstance(orientation, dict) else {}
    domain_volumes = summary.get("domain_tag_volumes")
    domain_volumes = (
        domain_volumes if isinstance(domain_volumes, dict) else {}
    )
    periodic_mismatch_fields = (
        "floquet_max_face_transform_fit_residual",
        "floquet_max_edge_midpoint_pairing_error",
        "floquet_max_face_midpoint_pairing_error",
        "floquet_edge_corner_constraint_phase_mismatch",
        "floquet_x_face_mismatch",
        "floquet_y_face_mismatch",
        "floquet_edge_corner_mismatch",
    )
    periodic_mismatches = [
        summary.get(name) for name in periodic_mismatch_fields
    ]
    backend_contract = backend_qualification.get("contract")
    backend_contract = (
        set(backend_contract) if isinstance(backend_contract, list) else set()
    )

    checks = {
        "fixed_rectangular_stage4_config": (
            config.get("stage_case") == "stage4_block_grating"
            and config.get("geometry_kind") == "rectangular_block_grating"
            and config.get("mesh_cell_type_resolved") == "hexahedron"
            and config.get("nedelec_degree") == 6
            and config.get("mesh_target_size") == 10.0
            and config.get("use_floquet_xy") is True
            and config.get("stage4_boundary_model") == "dtn_port"
            and config.get("stage4_dtn_assembly") == "auxiliary"
        ),
        "fixed_task034_physics": (
            config.get("lambda0") == 13.5
            and config.get("incident_theta_deg") == 80.0
            and config.get("incident_phi_deg") == 0.0
            and config.get("period_x") == 50.0
            and config.get("period_y") == 25.0
            and config.get("z_min") == -10.0
            and config.get("z_max") == 130.0
            and config.get("grating_height") == 120.0
            and config.get("grating_width_x") == 17.0
            and config.get("grating_width_y") == 25.0
            and config.get("scattering_background") == "layered"
            and config.get("polarization_kind") == "s"
        ),
        "mesh_and_tag_identity": (
            mesh_identity.get("partition_independent_mesh_sha256")
            == TASK035D_H10_MESH_SHA256
            and mesh_identity.get("cell_tag_sha256")
            == TASK035D_H10_CELL_TAG_SHA256
            and mesh_identity.get("facet_tag_sha256")
            == TASK035D_H10_FACET_TAG_SHA256
            and mesh_identity.get("global_cell_count") == 252
            and mesh_identity.get("mesh_cells_resolved") == [6, 3, 14]
            and summary.get("mesh_cells_resolved") == [6, 3, 14]
            and (summary.get("mesh_material_plane_alignment") or {}).get(
                "all_aligned"
            )
            is True
        ),
        "material_volume_identity": (
            math.isclose(
                float(domain_volumes.get("air", math.nan)),
                111_500.0,
                rel_tol=1.0e-12,
                abs_tol=1.0e-8,
            )
            and math.isclose(
                float(domain_volumes.get("substrate", math.nan)),
                12_500.0,
                rel_tol=1.0e-12,
                abs_tol=1.0e-8,
            )
            and math.isclose(
                float(domain_volumes.get("grating", math.nan)),
                51_000.0,
                rel_tol=1.0e-12,
                abs_tol=1.0e-8,
            )
        ),
        "uniform_container_periodic_orientation": (
            summary.get("use_floquet_xy") is True
            and summary.get("floquet_num_slave_edges")
            == summary.get("floquet_num_matched_master_edges")
            and summary.get("floquet_num_slave_faces")
            == summary.get("floquet_num_matched_master_faces")
            and all(
                isinstance(value, (int, float))
                and abs(float(value)) <= 1.0e-12
                for value in periodic_mismatches
            )
            and orientation.get("uses_exact_basix_entity_transforms")
            is True
            and orientation.get("uses_local_moment_fit") is False
            and orientation.get("used_full_boundary_gather") is False
            and orientation.get("created_dense_boundary_square") is False
        ),
        "variable_p_backend_actual": (
            summary.get("stage4_full3d_assembly_backend_actual")
            == TASK035D_CASE097_BACKEND
            and summary.get("stage4_variable_p_active") is True
            and backend_qualification.get("status") == "qualified"
            and backend_qualification.get("qualified_scope") is True
            and backend_qualification.get("element_contract")
            == "exact_sequence_variable_p4_p5_p6_in_p6_container"
            and {
                "geometry_bound_inactive_row_free_variable_p",
                "floquet_slave_elimination_before_global_insertion",
                "full_recovery_and_explicit_residual",
            }.issubset(backend_contract)
        ),
        "active_fe_dof_gate": (
            summary.get("num_actual_conforming_active_fe_dofs")
            == active_fe_dofs
            and summary.get("num_actual_conforming_active_fe_dofs") <= 90_000
        ),
        "active_periodic_trace_rows": (
            summary.get("num_active_trace_dofs")
            == periodic_trace_rows
        ),
        "active_solve_rows": (
            summary.get("num_active_condensed_dofs")
            == solve_rows
            and matrix.get("matrix_rows") == solve_rows
        ),
        "dtn_rows": (
            summary.get("stage4_dtn_num_auxiliary_dofs")
            == dtn_rows
        ),
        "matrix_nonzero_and_no_dynamic_reallocation": (
            isinstance(matrix.get("matrix_nnz_used"), (int, float))
            and float(matrix["matrix_nnz_used"]) > 0.0
            and matrix.get("matrix_mallocs") == 0.0
        ),
        "direct_factor_inventory": (
            factor_inventory.get("available") is True
            and factor_inventory.get("factor_solver_type") == "mumps"
            and factor_matrix.get("matrix_rows") == solve_rows
            and isinstance(
                factor_matrix.get("matrix_nnz_used"),
                (int, float),
            )
            and float(factor_matrix["matrix_nnz_used"]) > 0.0
        ),
        "degree_plan_identity": (
            degree_plan.get("cell_degree_plan_sha256")
            == plan_content_sha256
            and degree_plan.get("mesh_cell_box_catalog_sha256")
            == TASK035D_T30_GEOMETRY_CATALOG_SHA256
            and degree_plan.get("cell_degree_counts")
            == cell_degree_counts
        ),
        "degree_plan_active_dimensions": (
            degree_plan.get("active_rows") == active_fe_dofs
            and degree_plan.get("active_trace_rows")
            == active_trace_rows
        ),
        "periodic_identity": (
            periodic.get("pass") is True
            and periodic.get("mpi_size") == 8
            and periodic.get("independent_periodic_trace_rows")
            == periodic_trace_rows
            and periodic.get("inactive_p6_rows_globally_numbered") is False
        ),
        "inactive_rows_absent": (
            audit.get("full_p6_global_matrix_allocated") is False
            and audit.get("inactive_p6_rows_globally_numbered") is False
            and audit.get("active_fe_dof_gate_pass") is True
        ),
        "variable_p_audit_chain": (
            audit.get("schema_version")
            == "task035d.variable-p-assembly-reduction.v1"
            and audit.get("status")
            == "variable_p_assembly_time_reduction_built"
            and audit.get("pass") is True
            and degree_plan.get("pass") is True
            and periodic.get("pass") is True
            and global_transfer.get("pass") is True
            and condensed_system.get("pass") is True
            and condensed_system.get("status")
            == "variable_p_condensed_trace_matrix_pass"
            and degree_plan.get("mpi_size") == 8
            and periodic.get("mpi_size") == 8
            and global_transfer.get("mpi_size") == 8
            and condensed_system.get("mpi_size") == 8
        ),
        "trace_only_gate": (
            summary.get("stage4_dtn_variable_p_trace_only_gate_pass") is True
            and summary.get(
                "stage4_dtn_variable_p_auxiliary_interior_columns_allocated"
            )
            is False
            and summary.get(
                "stage4_dtn_variable_p_auxiliary_interior_column_bytes_local_max"
            )
            == 0
            and summary.get(
                "stage4_dtn_variable_p_trace_functional_count"
            )
            == 81
            and isinstance(
                summary.get(
                    "stage4_dtn_variable_p_removed_interior_max_abs"
                ),
                (int, float),
            )
            and math.isfinite(
                float(
                    summary[
                        "stage4_dtn_variable_p_removed_interior_max_abs"
                    ]
                )
            )
            and summary[
                "stage4_dtn_variable_p_removed_interior_max_abs"
            ]
            >= 0.0
        ),
        "full_field_recovery": (
            recovery.get("status") == "variable_p_full_field_recovery_pass"
            and recovery.get("pass") is True
        ),
        "full_explicit_true_residual": (
            isinstance(
                full_residual.get("linear_system_relative_residual"),
                (int, float),
            )
            and float(
                full_residual["linear_system_relative_residual"]
            )
            <= 1.0e-9
            and full_residual.get("linear_system_relative_residual")
            == summary.get("linear_system_relative_residual")
        ),
        "eliminated_interior_residual": (
            isinstance(
                full_residual.get(
                    "eliminated_cell_interior_residual_norm"
                ),
                (int, float),
            )
            and float(
                full_residual[
                    "eliminated_cell_interior_residual_norm"
                ]
            )
            <= 1.0e-9
        ),
        "ordinary_default_unchanged": (
            audit.get("ordinary_default_changed") is False
            and config.get("stage4_full3d_assembly_backend")
            == TASK035D_CASE097_BACKEND
            and backend_audit.get("ordinary_default_unchanged") is True
            and backend_audit.get("selection_source") == "public_port"
        ),
        "solver_lifecycle_release": (
            summary.get("direct_release_solver_before_postprocess") is True
            and summary.get("solver_objects_released_before_postprocess")
            is True
            and solver_release.get("petsc_garbage_cleanup_called") is True
            and heap_trim.get("supported_on_all_ranks") is True
            and heap_trim.get("succeeded_on_all_ranks") is True
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": schema_version,
        "status": (
            pass_status
            if not failures
            else fail_status
        ),
        "pass": not failures,
        "checks": checks,
        "failures": failures,
        "candidate": candidate_name,
        "accuracy_credit": "structural_and_residual_only",
    }


def task035d_case097_t30_solver_gate(
    solver_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    """Check the frozen T30 variable-p reduction identity."""

    return _task035d_case097_solver_gate(
        solver_summary,
        candidate_name=TASK035D_T30_PLAN_NAME,
        active_fe_dofs=TASK035D_T30_ACTIVE_FE_DOFS,
        active_trace_rows=TASK035D_T30_ACTIVE_TRACE_ROWS,
        periodic_trace_rows=TASK035D_T30_PERIODIC_TRACE_ROWS,
        solve_rows=TASK035D_T30_SOLVE_ROWS,
        dtn_rows=TASK035D_T30_DTN_ROWS,
        plan_content_sha256=TASK035D_T30_PLAN_CONTENT_SHA256,
        cell_degree_counts=TASK035D_T30_CELL_DEGREE_COUNTS,
        schema_version="task035d.case097-t30-solver-gate.v1",
        pass_status="task035d_t30_solver_identity_pass",
        fail_status="task035d_t30_solver_identity_fail",
    )


def task035d_case097_sidewall_guard_solver_gate(
    solver_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    """Check the frozen sidewall-z0 guard variable-p reduction identity."""

    return _task035d_case097_solver_gate(
        solver_summary,
        candidate_name=TASK035D_SIDEWALL_GUARD_PLAN_NAME,
        active_fe_dofs=TASK035D_SIDEWALL_GUARD_ACTIVE_FE_DOFS,
        active_trace_rows=TASK035D_SIDEWALL_GUARD_ACTIVE_TRACE_ROWS,
        periodic_trace_rows=TASK035D_SIDEWALL_GUARD_PERIODIC_TRACE_ROWS,
        solve_rows=TASK035D_SIDEWALL_GUARD_SOLVE_ROWS,
        dtn_rows=TASK035D_SIDEWALL_GUARD_DTN_ROWS,
        plan_content_sha256=TASK035D_SIDEWALL_GUARD_PLAN_CONTENT_SHA256,
        cell_degree_counts=TASK035D_SIDEWALL_GUARD_CELL_DEGREE_COUNTS,
        schema_version=(
            "task035d.case097-sidewall-z0-guard-solver-gate.v1"
        ),
        pass_status=(
            "task035d_sidewall_z0_guard_solver_identity_pass"
        ),
        fail_status=(
            "task035d_sidewall_z0_guard_solver_identity_fail"
        ),
    )


def task035d_case097_local_h_solver_gate(
    solver_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    """Check the exact h15 local-h reduction identity before physics review."""

    summary = solver_summary if isinstance(solver_summary, dict) else {}
    config = summary.get("config")
    config = config if isinstance(config, dict) else {}
    matrix = summary.get("matrix_stats")
    matrix = matrix if isinstance(matrix, dict) else {}
    audit = summary.get("cell_static_condensation")
    audit = audit if isinstance(audit, dict) else {}
    local_h = audit.get("local_h")
    local_h = local_h if isinstance(local_h, dict) else {}
    mesh = local_h.get("mesh")
    mesh = mesh if isinstance(mesh, dict) else {}
    forest = mesh.get("forest")
    forest = forest if isinstance(forest, dict) else {}
    carrier = mesh.get("carrier")
    carrier = carrier if isinstance(carrier, dict) else {}
    degree_plan = audit.get("degree_plan")
    degree_plan = degree_plan if isinstance(degree_plan, dict) else {}
    physical = local_h.get("physical_trace")
    physical = physical if isinstance(physical, dict) else {}
    trace = audit.get("trace_constraints")
    trace = trace if isinstance(trace, dict) else {}
    condensed = audit.get("condensed_system")
    condensed = condensed if isinstance(condensed, dict) else {}
    transfer = audit.get("global_transfer")
    transfer = transfer if isinstance(transfer, dict) else {}
    recovery = audit.get("recovery")
    recovery = recovery if isinstance(recovery, dict) else {}
    trace_recovery = recovery.get("trace_constraint_recovery")
    trace_recovery = (
        trace_recovery if isinstance(trace_recovery, dict) else {}
    )
    residual = audit.get("full_explicit_true_residual")
    residual = residual if isinstance(residual, dict) else {}
    qualification = summary.get(
        "stage4_full3d_assembly_backend_qualification"
    )
    qualification = (
        qualification if isinstance(qualification, dict) else {}
    )
    backend_audit = summary.get("stage4_full3d_assembly_backend_audit")
    backend_audit = (
        backend_audit if isinstance(backend_audit, dict) else {}
    )
    backend_contract = qualification.get("contract")
    backend_contract = (
        set(backend_contract) if isinstance(backend_contract, list) else set()
    )
    factor = summary.get("stage4_dtn_factor_inventory")
    factor = factor if isinstance(factor, dict) else {}
    factor_matrix = factor.get("matrix_stats")
    factor_matrix = (
        factor_matrix if isinstance(factor_matrix, dict) else {}
    )
    release = summary.get("solver_release_audit")
    release = release if isinstance(release, dict) else {}
    heap_trim = release.get("process_heap_trim")
    heap_trim = heap_trim if isinstance(heap_trim, dict) else {}
    domain_volumes = summary.get("domain_tag_volumes")
    domain_volumes = (
        domain_volumes if isinstance(domain_volumes, dict) else {}
    )
    checks = {
        "fixed_rectangular_h15_config": (
            config.get("stage_case") == "stage4_block_grating"
            and config.get("geometry_kind") == "rectangular_block_grating"
            and config.get("mesh_cell_type_resolved") == "hexahedron"
            and config.get("nedelec_degree") == 6
            and config.get("mesh_target_size") == 15.0
            and config.get("use_floquet_xy") is True
            and config.get("stage4_boundary_model") == "dtn_port"
            and config.get("stage4_dtn_assembly") == "auxiliary"
            and config.get("stage4_variable_p_cell_degree_plan") is None
            and isinstance(
                config.get("stage4_local_h_refinement_plan"),
                str,
            )
        ),
        "fixed_task034_physics": (
            config.get("lambda0") == 13.5
            and config.get("incident_theta_deg") == 80.0
            and config.get("incident_phi_deg") == 0.0
            and config.get("period_x") == 50.0
            and config.get("period_y") == 25.0
            and config.get("z_min") == -10.0
            and config.get("z_max") == 130.0
            and config.get("grating_height") == 120.0
            and config.get("grating_width_x") == 17.0
            and config.get("grating_width_y") == 25.0
            and config.get("scattering_background") == "layered"
            and config.get("polarization_kind") == "s"
        ),
        "material_volume_identity": (
            math.isclose(
                float(domain_volumes.get("air", math.nan)),
                111_500.0,
                rel_tol=1.0e-12,
                abs_tol=1.0e-8,
            )
            and math.isclose(
                float(domain_volumes.get("substrate", math.nan)),
                12_500.0,
                rel_tol=1.0e-12,
                abs_tol=1.0e-8,
            )
            and math.isclose(
                float(domain_volumes.get("grating", math.nan)),
                51_000.0,
                rel_tol=1.0e-12,
                abs_tol=1.0e-8,
            )
        ),
        "local_h_backend_actual": (
            summary.get("stage4_full3d_assembly_backend_actual")
            == TASK035D_CASE097_BACKEND
            and summary.get("stage4_variable_p_active") is True
            and summary.get("stage4_local_h_active") is True
            and qualification.get("status") == "qualified"
            and qualification.get("qualified_scope") is True
            and qualification.get("element_contract")
            == (
                "exact_sequence_balanced_local_h_fixed_trace_"
                "variable_cell_interior"
            )
            and {
                "geometry_bound_balanced_local_h_hanging_trace_elimination",
                "floquet_slave_elimination_before_global_insertion",
                "full_recovery_and_explicit_residual",
            }.issubset(backend_contract)
        ),
        "local_h_mesh_identity": (
            mesh.get("pass") is True
            and mesh.get("plan_file_sha256")
            == TASK035D_LOCAL_H_PLAN_FILE_SHA256
            and mesh.get("base_config_identity_sha256")
            == TASK035D_LOCAL_H_BASE_CONFIG_SHA256
            and mesh.get("trace_degree") == 5
            and mesh.get("cell_interior_degree") == 6
            and mesh.get("root_cell_count") == TASK035D_LOCAL_H_ROOT_CELLS
            and mesh.get("leaf_cell_count") == TASK035D_LOCAL_H_LEAF_CELLS
            and mesh.get("hanging_patch_count")
            == TASK035D_LOCAL_H_HANGING_PATCHES
            and forest.get("leaf_catalog_sha256")
            == TASK035D_LOCAL_H_LEAF_CATALOG_SHA256
            and forest.get("hanging_face_catalog_sha256")
            == TASK035D_LOCAL_H_HANGING_CATALOG_SHA256
            and carrier.get("canonical_connectivity_sha256")
            == TASK035D_LOCAL_H_CARRIER_SHA256
            and carrier.get("physical_facet_catalog_sha256")
            == TASK035D_LOCAL_H_PHYSICAL_FACET_SHA256
            and carrier.get("material_catalog_sha256")
            == TASK035D_LOCAL_H_MATERIAL_SHA256
            and carrier.get("checks", {}).get(
                "all_artificial_exterior_is_hanging"
            )
            is True
        ),
        "local_h_reduction_identity": (
            local_h.get("pass") is True
            and summary.get("stage4_local_h_constraint_audit") == local_h
            and local_h.get("raw_broken_active_fe_dofs")
            == TASK035D_LOCAL_H_RAW_ACTIVE_FE_DOFS
            and local_h.get("raw_broken_trace_rows")
            == TASK035D_LOCAL_H_RAW_TRACE_ROWS
            and local_h.get("hanging_slave_rows")
            == TASK035D_LOCAL_H_HANGING_SLAVE_ROWS
            and local_h.get("periodic_slave_rows")
            == TASK035D_LOCAL_H_PERIODIC_SLAVE_ROWS
            and local_h.get("actual_full3d_equivalent_active_fe_dofs")
            == TASK035D_LOCAL_H_ACTIVE_FE_DOFS
            and local_h.get("independent_trace_rows")
            == TASK035D_LOCAL_H_INDEPENDENT_TRACE_ROWS
            and local_h.get("active_fe_dof_gate_pass") is True
        ),
        "physical_trace_identity": (
            physical.get("pass") is True
            and physical.get("mpi_size") == 8
            and physical.get("degree") == 5
            and physical.get("physical_authority_sha256")
            == TASK035D_LOCAL_H_PHYSICAL_AUTHORITY_SHA256
        ),
        "combined_constraint_identity": (
            audit.get("periodic_constraints") is None
            and trace.get("pass") is True
            and trace.get("mpi_size") == 8
            and trace.get("constraint_kinds") == ["hanging", "floquet"]
            and trace.get("raw_trace_rows")
            == TASK035D_LOCAL_H_RAW_TRACE_ROWS
            and trace.get("independent_trace_rows")
            == TASK035D_LOCAL_H_INDEPENDENT_TRACE_ROWS
            and trace.get("hanging_slave_rows")
            == TASK035D_LOCAL_H_HANGING_SLAVE_ROWS
            and trace.get("periodic_slave_rows")
            == TASK035D_LOCAL_H_PERIODIC_SLAVE_ROWS
            and trace.get("flattened_graph_sha256")
            == TASK035D_LOCAL_H_FLATTENED_GRAPH_SHA256
            and trace.get("canonical_cell_graph_sha256")
            == TASK035D_LOCAL_H_CELL_GRAPH_SHA256
            and trace.get("pde_launch_ownership_gate") is True
            and trace.get(
                "hanging_or_floquet_slave_rows_globally_numbered"
            )
            is False
        ),
        "degree_plan_identity": (
            degree_plan.get("pass") is True
            and degree_plan.get("mpi_size") == 8
            and degree_plan.get("cell_count")
            == TASK035D_LOCAL_H_LEAF_CELLS
            and degree_plan.get("cell_degree_counts")
            == {"p4": 0, "p5": 0, "p6": TASK035D_LOCAL_H_LEAF_CELLS}
            and degree_plan.get("trace_degree") == 5
            and degree_plan.get("cell_interior_degree") == 6
            and degree_plan.get("active_rows")
            == TASK035D_LOCAL_H_RAW_ACTIVE_FE_DOFS
            and degree_plan.get("active_trace_rows")
            == TASK035D_LOCAL_H_RAW_TRACE_ROWS
            and degree_plan.get("mesh_cell_box_catalog_sha256")
            == TASK035D_LOCAL_H_BOX_CATALOG_SHA256
        ),
        "active_dimension_gates": (
            summary.get("num_raw_broken_active_fe_dofs")
            == TASK035D_LOCAL_H_RAW_ACTIVE_FE_DOFS
            and summary.get("num_actual_conforming_active_fe_dofs")
            == TASK035D_LOCAL_H_ACTIVE_FE_DOFS
            and summary.get("num_active_trace_dofs")
            == TASK035D_LOCAL_H_INDEPENDENT_TRACE_ROWS
            and summary.get("num_active_condensed_dofs")
            == TASK035D_LOCAL_H_SOLVE_ROWS
            and summary.get("stage4_dtn_num_auxiliary_dofs")
            == TASK035D_LOCAL_H_DTN_ROWS
            and matrix.get("matrix_rows") == TASK035D_LOCAL_H_SOLVE_ROWS
        ),
        "matrix_nonzero_and_exact_preallocation": (
            isinstance(matrix.get("matrix_nnz_used"), (int, float))
            and float(matrix["matrix_nnz_used"]) > 0.0
            and matrix.get("matrix_mallocs") == 0.0
        ),
        "direct_factor_inventory": (
            factor.get("available") is True
            and factor.get("factor_solver_type") == "mumps"
            and factor_matrix.get("matrix_rows")
            == TASK035D_LOCAL_H_SOLVE_ROWS
            and isinstance(
                factor_matrix.get("matrix_nnz_used"),
                (int, float),
            )
            and float(factor_matrix["matrix_nnz_used"]) > 0.0
        ),
        "assembly_reduction_chain": (
            audit.get("schema_version")
            == "task035d.variable-p-assembly-reduction.v1"
            and audit.get("status")
            == "variable_p_assembly_time_reduction_built"
            and audit.get("pass") is True
            and condensed.get("pass") is True
            and condensed.get("mpi_size") == 8
            and condensed.get("schema_version")
            == "task035d.variable-p-condensed-trace-system.v1"
            and condensed.get("status")
            == "variable_p_condensed_trace_matrix_pass"
            and condensed.get("active_full3d_rows_before_condensation")
            == TASK035D_LOCAL_H_RAW_ACTIVE_FE_DOFS
            and condensed.get(
                "active_trace_rows_before_constraint_elimination"
            )
            == TASK035D_LOCAL_H_RAW_TRACE_ROWS
            and condensed.get("active_trace_rows")
            == TASK035D_LOCAL_H_INDEPENDENT_TRACE_ROWS
            and condensed.get("appended_rows") == TASK035D_LOCAL_H_DTN_ROWS
            and condensed.get(
                "floquet_elimination_applied_before_insertion"
            )
            is True
            and condensed.get(
                "hanging_elimination_applied_before_insertion"
            )
            is True
            and condensed.get(
                "trace_constraint_elimination_applied_before_insertion"
            )
            is True
            and set(condensed.get("trace_constraint_kinds") or ())
            == {"hanging", "floquet"}
            and condensed.get(
                "hanging_or_floquet_slave_rows_globally_numbered"
            )
            is False
            and transfer.get("pass") is True
            and transfer.get("mpi_size") == 8
            and audit.get("full_p6_global_matrix_allocated") is False
            and audit.get("inactive_p6_rows_globally_numbered") is False
            and audit.get("active_fe_dof_gate_pass") is True
        ),
        "trace_only_dtn": (
            summary.get("stage4_dtn_variable_p_trace_only_gate_pass") is True
            and summary.get(
                "stage4_dtn_variable_p_auxiliary_interior_columns_allocated"
            )
            is False
            and summary.get(
                "stage4_dtn_variable_p_auxiliary_interior_column_bytes_local_max"
            )
            == 0
            and summary.get(
                "stage4_dtn_variable_p_trace_functional_count"
            )
            == 81
        ),
        "full_field_and_hanging_recovery": (
            recovery.get("status") == "variable_p_full_field_recovery_pass"
            and recovery.get("pass") is True
            and trace_recovery.get("pass") is True
            and trace_recovery.get("hanging_trace_recovery_explicitly_checked")
            is True
            and set(trace_recovery.get("constraint_kinds") or ())
            == {"hanging", "floquet"}
            and trace_recovery.get("covered_raw_trace_rows")
            == TASK035D_LOCAL_H_RAW_TRACE_ROWS
            and trace_recovery.get("expected_raw_trace_rows")
            == TASK035D_LOCAL_H_RAW_TRACE_ROWS
            and trace_recovery.get("maximum_abs_error", math.inf)
            <= 5.0e-11
            and trace_recovery.get("relative_l2_error", math.inf)
            <= 5.0e-11
        ),
        "full_explicit_true_residual": (
            isinstance(
                residual.get("linear_system_relative_residual"),
                (int, float),
            )
            and residual.get("linear_system_relative_residual")
            == summary.get("linear_system_relative_residual")
            and float(residual["linear_system_relative_residual"])
            <= 1.0e-9
            and float(
                residual.get(
                    "eliminated_cell_interior_residual_norm",
                    math.inf,
                )
            )
            <= 1.0e-9
        ),
        "ordinary_default_unchanged": (
            audit.get("ordinary_default_changed") is False
            and backend_audit.get("ordinary_default_unchanged") is True
            and backend_audit.get("selection_source") == "public_port"
            and config.get("stage4_full3d_assembly_backend")
            == TASK035D_CASE097_BACKEND
        ),
        "solver_lifecycle_release": (
            summary.get("direct_release_solver_before_postprocess") is True
            and summary.get("solver_objects_released_before_postprocess")
            is True
            and release.get("petsc_garbage_cleanup_called") is True
            and heap_trim.get("supported_on_all_ranks") is True
            and heap_trim.get("succeeded_on_all_ranks") is True
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": "task035d.case097-h15-local-h-solver-gate.v1",
        "status": (
            "task035d_h15_local_h_solver_identity_pass"
            if not failures
            else "task035d_h15_local_h_solver_identity_fail"
        ),
        "pass": not failures,
        "checks": checks,
        "failures": failures,
        "candidate": TASK035D_LOCAL_H_PLAN_NAME,
        "accuracy_credit": "structural_and_residual_only",
    }


def _task035d_case097_variable_interior_solver_gate(
    solver_summary: dict[str, Any] | None,
    *,
    spec: dict[str, Any],
) -> dict[str, Any]:
    """Check one exact local-h/variable-interior solver identity."""

    TASK035D_COMBINED_HP_PLAN_NAME = spec["candidate_name"]
    TASK035D_COMBINED_HP_PLAN_FILE_SHA256 = spec["plan_file_sha256"]
    TASK035D_COMBINED_HP_LEAF_CATALOG_SHA256 = spec[
        "leaf_catalog_sha256"
    ]
    TASK035D_COMBINED_HP_HANGING_CATALOG_SHA256 = spec[
        "hanging_catalog_sha256"
    ]
    TASK035D_COMBINED_HP_CARRIER_SHA256 = spec["carrier_sha256"]
    TASK035D_COMBINED_HP_PHYSICAL_FACET_SHA256 = spec[
        "physical_facet_sha256"
    ]
    TASK035D_COMBINED_HP_MATERIAL_SHA256 = spec["material_sha256"]
    TASK035D_COMBINED_HP_PHYSICAL_AUTHORITY_SHA256 = spec[
        "physical_authority_sha256"
    ]
    TASK035D_COMBINED_HP_FLATTENED_GRAPH_SHA256 = spec[
        "flattened_graph_sha256"
    ]
    TASK035D_COMBINED_HP_CELL_GRAPH_SHA256 = spec["cell_graph_sha256"]
    TASK035D_COMBINED_HP_BOX_CATALOG_SHA256 = spec[
        "box_catalog_sha256"
    ]
    TASK035D_COMBINED_HP_CELL_DEGREE_PLAN_SHA256 = spec[
        "cell_degree_plan_sha256"
    ]
    TASK035D_COMBINED_HP_ENTITY_DEGREE_SHA256 = spec[
        "entity_degree_sha256"
    ]
    TASK035D_COMBINED_HP_ROOT_CELLS = spec["root_cells"]
    TASK035D_COMBINED_HP_LEAF_CELLS = spec["leaf_cells"]
    TASK035D_COMBINED_HP_HANGING_PATCHES = spec["hanging_patches"]
    TASK035D_COMBINED_HP_RAW_ACTIVE_FE_DOFS = spec["raw_active_fe_dofs"]
    TASK035D_COMBINED_HP_RAW_TRACE_ROWS = spec["raw_trace_rows"]
    TASK035D_COMBINED_HP_HANGING_SLAVE_ROWS = spec[
        "hanging_slave_rows"
    ]
    TASK035D_COMBINED_HP_PERIODIC_SLAVE_ROWS = spec[
        "periodic_slave_rows"
    ]
    TASK035D_COMBINED_HP_ACTIVE_FE_DOFS = spec["active_fe_dofs"]
    TASK035D_COMBINED_HP_INDEPENDENT_TRACE_ROWS = spec[
        "independent_trace_rows"
    ]
    TASK035D_COMBINED_HP_DTN_ROWS = spec["dtn_rows"]
    TASK035D_COMBINED_HP_SOLVE_ROWS = spec["solve_rows"]
    TASK035D_COMBINED_HP_CELL_DEGREE_COUNTS = spec[
        "cell_degree_counts"
    ]

    summary = solver_summary if isinstance(solver_summary, dict) else {}
    config = summary.get("config")
    config = config if isinstance(config, dict) else {}
    matrix = summary.get("matrix_stats")
    matrix = matrix if isinstance(matrix, dict) else {}
    audit = summary.get("cell_static_condensation")
    audit = audit if isinstance(audit, dict) else {}
    local_h = audit.get("local_h")
    local_h = local_h if isinstance(local_h, dict) else {}
    mesh = local_h.get("mesh")
    mesh = mesh if isinstance(mesh, dict) else {}
    forest = mesh.get("forest")
    forest = forest if isinstance(forest, dict) else {}
    carrier = mesh.get("carrier")
    carrier = carrier if isinstance(carrier, dict) else {}
    degree_plan = audit.get("degree_plan")
    degree_plan = degree_plan if isinstance(degree_plan, dict) else {}
    physical = local_h.get("physical_trace")
    physical = physical if isinstance(physical, dict) else {}
    trace = audit.get("trace_constraints")
    trace = trace if isinstance(trace, dict) else {}
    condensed = audit.get("condensed_system")
    condensed = condensed if isinstance(condensed, dict) else {}
    transfer = audit.get("global_transfer")
    transfer = transfer if isinstance(transfer, dict) else {}
    recovery = audit.get("recovery")
    recovery = recovery if isinstance(recovery, dict) else {}
    trace_recovery = recovery.get("trace_constraint_recovery")
    trace_recovery = (
        trace_recovery if isinstance(trace_recovery, dict) else {}
    )
    residual = audit.get("full_explicit_true_residual")
    residual = residual if isinstance(residual, dict) else {}
    qualification = summary.get(
        "stage4_full3d_assembly_backend_qualification"
    )
    qualification = (
        qualification if isinstance(qualification, dict) else {}
    )
    backend_audit = summary.get("stage4_full3d_assembly_backend_audit")
    backend_audit = (
        backend_audit if isinstance(backend_audit, dict) else {}
    )
    backend_contract = qualification.get("contract")
    backend_contract = (
        set(backend_contract) if isinstance(backend_contract, list) else set()
    )
    factor = summary.get("stage4_dtn_factor_inventory")
    factor = factor if isinstance(factor, dict) else {}
    factor_matrix = factor.get("matrix_stats")
    factor_matrix = (
        factor_matrix if isinstance(factor_matrix, dict) else {}
    )
    release = summary.get("solver_release_audit")
    release = release if isinstance(release, dict) else {}
    heap_trim = release.get("process_heap_trim")
    heap_trim = heap_trim if isinstance(heap_trim, dict) else {}
    domain_volumes = summary.get("domain_tag_volumes")
    domain_volumes = (
        domain_volumes if isinstance(domain_volumes, dict) else {}
    )
    checks = {
        "fixed_rectangular_h15_config": (
            config.get("stage_case") == "stage4_block_grating"
            and config.get("geometry_kind") == "rectangular_block_grating"
            and config.get("mesh_cell_type_resolved") == "hexahedron"
            and config.get("nedelec_degree") == 6
            and config.get("mesh_target_size") == 15.0
            and config.get("use_floquet_xy") is True
            and config.get("stage4_boundary_model") == "dtn_port"
            and config.get("stage4_dtn_assembly") == "auxiliary"
            and config.get("stage4_variable_p_cell_degree_plan") is None
            and isinstance(
                config.get("stage4_local_h_refinement_plan"),
                str,
            )
        ),
        "fixed_task034_physics_and_volumes": (
            config.get("lambda0") == 13.5
            and config.get("incident_theta_deg") == 80.0
            and config.get("incident_phi_deg") == 0.0
            and config.get("period_x") == 50.0
            and config.get("period_y") == 25.0
            and config.get("z_min") == -10.0
            and config.get("z_max") == 130.0
            and config.get("grating_height") == 120.0
            and config.get("grating_width_x") == 17.0
            and config.get("grating_width_y") == 25.0
            and config.get("scattering_background") == "layered"
            and config.get("polarization_kind") == "s"
            and math.isclose(
                float(domain_volumes.get("air", math.nan)),
                111_500.0,
                rel_tol=1.0e-12,
                abs_tol=1.0e-8,
            )
            and math.isclose(
                float(domain_volumes.get("substrate", math.nan)),
                12_500.0,
                rel_tol=1.0e-12,
                abs_tol=1.0e-8,
            )
            and math.isclose(
                float(domain_volumes.get("grating", math.nan)),
                51_000.0,
                rel_tol=1.0e-12,
                abs_tol=1.0e-8,
            )
        ),
        "combined_backend_actual": (
            summary.get("stage4_full3d_assembly_backend_actual")
            == TASK035D_CASE097_BACKEND
            and summary.get("stage4_variable_p_active") is True
            and summary.get("stage4_local_h_active") is True
            and qualification.get("status") == "qualified"
            and qualification.get("qualified_scope") is True
            and qualification.get("element_contract")
            == (
                "exact_sequence_balanced_local_h_fixed_trace_"
                "variable_cell_interior"
            )
            and {
                "geometry_bound_balanced_local_h_hanging_trace_elimination",
                "floquet_slave_elimination_before_global_insertion",
                "full_recovery_and_explicit_residual",
            }.issubset(backend_contract)
        ),
        "mesh_identity": (
            mesh.get("pass") is True
            and mesh.get("plan_file_sha256")
            == TASK035D_COMBINED_HP_PLAN_FILE_SHA256
            and mesh.get("base_config_identity_sha256")
            == TASK035D_LOCAL_H_BASE_CONFIG_SHA256
            and mesh.get("trace_degree") == 5
            and mesh.get("cell_interior_degree") == 6
            and mesh.get("cell_interior_degree_counts")
            == TASK035D_COMBINED_HP_CELL_DEGREE_COUNTS
            and mesh.get("cell_interior_degree_plan_sha256")
            == TASK035D_COMBINED_HP_CELL_DEGREE_PLAN_SHA256
            and mesh.get("variable_cell_interior_degree") is True
            and mesh.get("root_cell_count")
            == TASK035D_COMBINED_HP_ROOT_CELLS
            and mesh.get("leaf_cell_count")
            == TASK035D_COMBINED_HP_LEAF_CELLS
            and mesh.get("hanging_patch_count")
            == TASK035D_COMBINED_HP_HANGING_PATCHES
            and forest.get("leaf_catalog_sha256")
            == TASK035D_COMBINED_HP_LEAF_CATALOG_SHA256
            and forest.get("hanging_face_catalog_sha256")
            == TASK035D_COMBINED_HP_HANGING_CATALOG_SHA256
            and carrier.get("canonical_connectivity_sha256")
            == TASK035D_COMBINED_HP_CARRIER_SHA256
            and carrier.get("physical_facet_catalog_sha256")
            == TASK035D_COMBINED_HP_PHYSICAL_FACET_SHA256
            and carrier.get("material_catalog_sha256")
            == TASK035D_COMBINED_HP_MATERIAL_SHA256
            and carrier.get("checks", {}).get(
                "all_artificial_exterior_is_hanging"
            )
            is True
        ),
        "combined_reduction_identity": (
            local_h.get("pass") is True
            and summary.get("stage4_local_h_constraint_audit") == local_h
            and local_h.get("raw_broken_active_fe_dofs")
            == TASK035D_COMBINED_HP_RAW_ACTIVE_FE_DOFS
            and local_h.get("raw_broken_trace_rows")
            == TASK035D_COMBINED_HP_RAW_TRACE_ROWS
            and local_h.get("hanging_slave_rows")
            == TASK035D_COMBINED_HP_HANGING_SLAVE_ROWS
            and local_h.get("periodic_slave_rows")
            == TASK035D_COMBINED_HP_PERIODIC_SLAVE_ROWS
            and local_h.get("actual_full3d_equivalent_active_fe_dofs")
            == TASK035D_COMBINED_HP_ACTIVE_FE_DOFS
            and local_h.get("independent_trace_rows")
            == TASK035D_COMBINED_HP_INDEPENDENT_TRACE_ROWS
            and local_h.get("active_fe_dof_gate_pass") is True
        ),
        "physical_and_constraint_identity": (
            physical.get("pass") is True
            and physical.get("mpi_size") == 8
            and physical.get("degree") == 5
            and physical.get("physical_authority_sha256")
            == TASK035D_COMBINED_HP_PHYSICAL_AUTHORITY_SHA256
            and audit.get("periodic_constraints") is None
            and trace.get("pass") is True
            and trace.get("mpi_size") == 8
            and trace.get("constraint_kinds") == ["hanging", "floquet"]
            and trace.get("raw_trace_rows")
            == TASK035D_COMBINED_HP_RAW_TRACE_ROWS
            and trace.get("independent_trace_rows")
            == TASK035D_COMBINED_HP_INDEPENDENT_TRACE_ROWS
            and trace.get("hanging_slave_rows")
            == TASK035D_COMBINED_HP_HANGING_SLAVE_ROWS
            and trace.get("periodic_slave_rows")
            == TASK035D_COMBINED_HP_PERIODIC_SLAVE_ROWS
            and trace.get("flattened_graph_sha256")
            == TASK035D_COMBINED_HP_FLATTENED_GRAPH_SHA256
            and trace.get("canonical_cell_graph_sha256")
            == TASK035D_COMBINED_HP_CELL_GRAPH_SHA256
            and trace.get("pde_launch_ownership_gate") is True
            and trace.get(
                "hanging_or_floquet_slave_rows_globally_numbered"
            )
            is False
        ),
        "variable_interior_degree_identity": (
            degree_plan.get("pass") is True
            and degree_plan.get("mpi_size") == 8
            and degree_plan.get("cell_count")
            == TASK035D_COMBINED_HP_LEAF_CELLS
            and degree_plan.get("cell_degree_counts")
            == TASK035D_COMBINED_HP_CELL_DEGREE_COUNTS
            and degree_plan.get("trace_degree") == 5
            and degree_plan.get("cell_interior_degree") == 6
            and degree_plan.get("cell_degree_plan_sha256")
            == TASK035D_COMBINED_HP_CELL_DEGREE_PLAN_SHA256
            and degree_plan.get(
                "geometry_canonical_entity_degree_sha256"
            )
            == TASK035D_COMBINED_HP_ENTITY_DEGREE_SHA256
            and degree_plan.get("variable_cell_interior_degree") is True
            and degree_plan.get("local_variable_trace_implemented") is False
            and degree_plan.get("complete_combined_hp_credit") is False
            and degree_plan.get(
                "cell_interior_p6_modes_globally_numbered_when_inactive"
            )
            is False
            and degree_plan.get("active_rows")
            == TASK035D_COMBINED_HP_RAW_ACTIVE_FE_DOFS
            and degree_plan.get("active_trace_rows")
            == TASK035D_COMBINED_HP_RAW_TRACE_ROWS
            and degree_plan.get("mesh_cell_box_catalog_sha256")
            == TASK035D_COMBINED_HP_BOX_CATALOG_SHA256
        ),
        "active_dimension_and_matrix_gates": (
            summary.get("num_raw_broken_active_fe_dofs")
            == TASK035D_COMBINED_HP_RAW_ACTIVE_FE_DOFS
            and summary.get("num_actual_conforming_active_fe_dofs")
            == TASK035D_COMBINED_HP_ACTIVE_FE_DOFS
            and summary.get("num_active_trace_dofs")
            == TASK035D_COMBINED_HP_INDEPENDENT_TRACE_ROWS
            and summary.get("num_active_condensed_dofs")
            == TASK035D_COMBINED_HP_SOLVE_ROWS
            and summary.get("stage4_dtn_num_auxiliary_dofs")
            == TASK035D_COMBINED_HP_DTN_ROWS
            and matrix.get("matrix_rows")
            == TASK035D_COMBINED_HP_SOLVE_ROWS
            and isinstance(matrix.get("matrix_nnz_used"), (int, float))
            and float(matrix["matrix_nnz_used"]) > 0.0
            and matrix.get("matrix_mallocs") == 0.0
            and factor.get("available") is True
            and factor.get("factor_solver_type") == "mumps"
            and factor_matrix.get("matrix_rows")
            == TASK035D_COMBINED_HP_SOLVE_ROWS
            and isinstance(
                factor_matrix.get("matrix_nnz_used"),
                (int, float),
            )
            and float(factor_matrix["matrix_nnz_used"]) > 0.0
        ),
        "assembly_reduction_chain": (
            audit.get("schema_version")
            == "task035d.variable-p-assembly-reduction.v1"
            and audit.get("status")
            == "variable_p_assembly_time_reduction_built"
            and audit.get("pass") is True
            and condensed.get("pass") is True
            and condensed.get("mpi_size") == 8
            and condensed.get("active_full3d_rows_before_condensation")
            == TASK035D_COMBINED_HP_RAW_ACTIVE_FE_DOFS
            and condensed.get(
                "active_trace_rows_before_constraint_elimination"
            )
            == TASK035D_COMBINED_HP_RAW_TRACE_ROWS
            and condensed.get("active_trace_rows")
            == TASK035D_COMBINED_HP_INDEPENDENT_TRACE_ROWS
            and condensed.get("appended_rows")
            == TASK035D_COMBINED_HP_DTN_ROWS
            and condensed.get(
                "interior_rhs_recovery_iterative_refinement_max_steps"
            )
            == 2
            and condensed.get(
                "floquet_elimination_applied_before_insertion"
            )
            is True
            and condensed.get(
                "hanging_elimination_applied_before_insertion"
            )
            is True
            and set(condensed.get("trace_constraint_kinds") or ())
            == {"hanging", "floquet"}
            and condensed.get(
                "hanging_or_floquet_slave_rows_globally_numbered"
            )
            is False
            and transfer.get("pass") is True
            and transfer.get("mpi_size") == 8
            and audit.get("full_p6_global_matrix_allocated") is False
            and audit.get("inactive_p6_rows_globally_numbered") is False
            and audit.get("active_fe_dof_gate_pass") is True
        ),
        "trace_only_dtn": (
            summary.get("stage4_dtn_variable_p_trace_only_gate_pass") is True
            and summary.get(
                "stage4_dtn_variable_p_auxiliary_interior_columns_allocated"
            )
            is False
            and summary.get(
                "stage4_dtn_variable_p_auxiliary_interior_column_bytes_local_max"
            )
            == 0
            and summary.get(
                "stage4_dtn_variable_p_trace_functional_count"
            )
            == 81
        ),
        "full_field_and_hanging_recovery": (
            recovery.get("status") == "variable_p_full_field_recovery_pass"
            and recovery.get("pass") is True
            and recovery.get(
                "interior_rhs_recovery_iterative_refinement_max_steps"
            )
            == 2
            and recovery.get("interior_trace_source")
            == "assembled_global_active_trace"
            and recovery.get(
                "trace_vector_assembled_before_interior_recovery"
            )
            is True
            and trace_recovery.get("pass") is True
            and trace_recovery.get("hanging_trace_recovery_explicitly_checked")
            is True
            and set(trace_recovery.get("constraint_kinds") or ())
            == {"hanging", "floquet"}
            and trace_recovery.get("covered_raw_trace_rows")
            == TASK035D_COMBINED_HP_RAW_TRACE_ROWS
            and trace_recovery.get("expected_raw_trace_rows")
            == TASK035D_COMBINED_HP_RAW_TRACE_ROWS
            and trace_recovery.get("maximum_abs_error", math.inf)
            <= 5.0e-11
            and trace_recovery.get("relative_l2_error", math.inf)
            <= 5.0e-11
        ),
        "full_explicit_true_residual": (
            isinstance(
                residual.get("linear_system_relative_residual"),
                (int, float),
            )
            and residual.get("linear_system_relative_residual")
            == summary.get("linear_system_relative_residual")
            and float(residual["linear_system_relative_residual"])
            <= 1.0e-9
            and float(
                residual.get(
                    "eliminated_cell_interior_residual_norm",
                    math.inf,
                )
            )
            <= 1.0e-9
        ),
        "ordinary_default_and_lifecycle": (
            audit.get("ordinary_default_changed") is False
            and backend_audit.get("ordinary_default_unchanged") is True
            and backend_audit.get("selection_source") == "public_port"
            and config.get("stage4_full3d_assembly_backend")
            == TASK035D_CASE097_BACKEND
            and summary.get("direct_release_solver_before_postprocess") is True
            and summary.get("solver_objects_released_before_postprocess")
            is True
            and release.get("petsc_garbage_cleanup_called") is True
            and heap_trim.get("supported_on_all_ranks") is True
            and heap_trim.get("succeeded_on_all_ranks") is True
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": spec["solver_schema"],
        "status": (
            spec["solver_pass_status"]
            if not failures
            else spec["solver_fail_status"]
        ),
        "pass": not failures,
        "checks": checks,
        "failures": failures,
        "candidate": TASK035D_COMBINED_HP_PLAN_NAME,
        "accuracy_credit": "structural_and_residual_only",
        "complete_combined_hp_credit": False,
    }


def task035d_case097_combined_hp_solver_gate(
    solver_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    """Check the symmetric local-h/variable-interior solver identity."""

    return _task035d_case097_variable_interior_solver_gate(
        solver_summary,
        spec=_COMBINED_HP_GATE_SPEC,
    )


def task035d_case097_hp_factorial_bridge_solver_gate(
    solver_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    """Check the one-sided-h/remote-interior-p factorial bridge."""

    return _task035d_case097_variable_interior_solver_gate(
        solver_summary,
        spec=_HP_FACTORIAL_BRIDGE_GATE_SPEC,
    )


__all__ = [
    "TASK035D_CASE097_BACKEND",
    "TASK035D_COMBINED_HP_ACTIVE_FE_DOFS",
    "TASK035D_COMBINED_HP_AUTHORITY_FILE_SHA256",
    "TASK035D_COMBINED_HP_AUTHORITY_PATH",
    "TASK035D_COMBINED_HP_PLAN_FILE_SHA256",
    "TASK035D_COMBINED_HP_PLAN_NAME",
    "TASK035D_COMBINED_HP_PLAN_PATH",
    "TASK035D_COMBINED_HP_SOLVE_ROWS",
    "TASK035D_H10_CELL_TAG_SHA256",
    "TASK035D_H10_FACET_TAG_SHA256",
    "TASK035D_H10_MESH_SHA256",
    "TASK035D_HP_FACTORIAL_BRIDGE_ACTIVE_FE_DOFS",
    "TASK035D_HP_FACTORIAL_BRIDGE_AUTHORITY_FILE_SHA256",
    "TASK035D_HP_FACTORIAL_BRIDGE_AUTHORITY_PATH",
    "TASK035D_HP_FACTORIAL_BRIDGE_PLAN_FILE_SHA256",
    "TASK035D_HP_FACTORIAL_BRIDGE_PLAN_NAME",
    "TASK035D_HP_FACTORIAL_BRIDGE_PLAN_PATH",
    "TASK035D_HP_FACTORIAL_BRIDGE_SOLVE_ROWS",
    "TASK035D_LOCAL_H_ACTIVE_FE_DOFS",
    "TASK035D_LOCAL_H_AUTHORITY_FILE_SHA256",
    "TASK035D_LOCAL_H_AUTHORITY_PATH",
    "TASK035D_LOCAL_H_DTN_ROWS",
    "TASK035D_LOCAL_H_INDEPENDENT_TRACE_ROWS",
    "TASK035D_LOCAL_H_PLAN_FILE_SHA256",
    "TASK035D_LOCAL_H_PLAN_NAME",
    "TASK035D_LOCAL_H_PLAN_PATH",
    "TASK035D_LOCAL_H_RAW_ACTIVE_FE_DOFS",
    "TASK035D_LOCAL_H_RAW_TRACE_ROWS",
    "TASK035D_LOCAL_H_SOLVE_ROWS",
    "TASK035D_SIDEWALL_GUARD_ACTIVE_FE_DOFS",
    "TASK035D_SIDEWALL_GUARD_ACTIVE_TRACE_ROWS",
    "TASK035D_SIDEWALL_GUARD_AUTHORITY_FILE_SHA256",
    "TASK035D_SIDEWALL_GUARD_AUTHORITY_PATH",
    "TASK035D_SIDEWALL_GUARD_CELL_DEGREE_COUNTS",
    "TASK035D_SIDEWALL_GUARD_DIAGNOSTIC_PATH",
    "TASK035D_SIDEWALL_GUARD_DIAGNOSTIC_SHA256",
    "TASK035D_SIDEWALL_GUARD_DTN_ROWS",
    "TASK035D_SIDEWALL_GUARD_PERIODIC_TRACE_ROWS",
    "TASK035D_SIDEWALL_GUARD_PLAN_CONTENT_SHA256",
    "TASK035D_SIDEWALL_GUARD_PLAN_FILE_SHA256",
    "TASK035D_SIDEWALL_GUARD_PLAN_NAME",
    "TASK035D_SIDEWALL_GUARD_PLAN_PATH",
    "TASK035D_SIDEWALL_GUARD_SOLVE_ROWS",
    "TASK035D_T30_ACTIVE_FE_DOFS",
    "TASK035D_T30_ACTIVE_TRACE_ROWS",
    "TASK035D_T30_AUTHORITY_FILE_SHA256",
    "TASK035D_T30_AUTHORITY_PATH",
    "TASK035D_T30_DTN_ROWS",
    "TASK035D_T30_PERIODIC_TRACE_ROWS",
    "TASK035D_T30_PLAN_CONTENT_SHA256",
    "TASK035D_T30_PLAN_FILE_SHA256",
    "TASK035D_T30_PLAN_PATH",
    "TASK035D_T30_SOLVE_ROWS",
    "task035d_case097_local_h_plan_authority_gate",
    "task035d_case097_local_h_solver_gate",
    "task035d_case097_combined_hp_plan_authority_gate",
    "task035d_case097_combined_hp_solver_gate",
    "task035d_case097_hp_factorial_bridge_plan_authority_gate",
    "task035d_case097_hp_factorial_bridge_solver_gate",
    "task035d_case097_plan_authority_gate",
    "task035d_case097_sidewall_guard_plan_authority_gate",
    "task035d_case097_sidewall_guard_solver_gate",
    "task035d_case097_t30_solver_gate",
]
