"""Explicit Task042 research profiles; historical inputs retain their contracts."""

from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parents[2]
TASK042_PROFILES = {
    **{"task042_v17_"+name.lower(): "V17-"+name
       for name in ("PREFLIGHT", "GPOLY", "GNN", "GMRES_GPOLY", "GMRES_GNN", "VERIFY")},
    "task042_shared_f1_reference_v1": "F1-reference",
    "task042_shared_f1_b0_v1": "F1-B0",
    "task042_shared_f2_teacher_v1": "F2-teacher",
    "task042_shared_f2_oracle_v1": "F2-oracle",
    "task042_shared_f3_train_v1": "F3-train",
    "task042_shared_f4_b0_v1": "F4-B0",
    "task042_shared_f4_linear_v1": "F4-LIN",
    "task042_shared_f4_neural_v1": "F4-NN",
    "task042_shared_v3_reuse_diagnostic": "V3-reuse",
    "task042_shared_v3_cell_port_overlap": "V3-overlap",
    "task042_shared_v4_action_algebra": "V4-P0",
    "task042_shared_v4_error_snapshots": "V4-P1",
    "task042_shared_v4_error_space": "V4-P2-ERROR",
    "task042_shared_v4_oldpod_space": "V4-P2-OLDPOD",
    "task042_shared_v4_error_diagnostic": "V4-P3-ERROR",
    "task042_shared_v4_oldpod_diagnostic": "V4-P3-OLDPOD",
    "task042_shared_v4_fresh_qualification": "V4-P4",
    "task042_shared_v4_fresh_generation": "V4-P4-GENERATE",
    "task042_shared_v5_common_states": "V5-D0",
    "task042_shared_v5_offline_coverage": "V5-D1",
    "task042_shared_v5_oldpod_localization": "V5-OLDPOD",
    "task042_shared_v5_error_localization": "V5-ERROR",
    "task042_v6_geometry_trace_interface": "V6-FE-INTERFACE",
    "task042_v6_neural_packet_vjp": "V6-ML-INTERFACE",
    "task042_v7_material_inventory": "V7-M0",
    "task042_v7_real_fe_interface": "V7-M1-FE",
    "task042_v7_real_equation_gradient": "V7-M1-GRAD",
    "task042_v7_neural_trace": "V7-M2-NEURAL",
    "task042_v7_free_fe_opt": "V7-M2-FREE",
    "task042_v7_fe_lsqr": "V7-M2-LSQR",
    "task042_v7_same_mesh_p3_reference": "V7-M3-REFERENCE",
    "task042_v7_same_mesh_p3_verification": "V7-M3-VERIFY",
    "task042_v8_reuse_inventory": "V8-C0",
    "task042_v8_column_setup": "V8-C2-SETUP",
    "task042_v8_scaled_lsqr": "V8-C2-LSQR",
    "task042_v8_scaled_verification": "V8-C2-VERIFY",
    "task042_v8_batch_equivalence": "V8-C3-EQUIVALENCE",
    "task042_v8_batch_microbenchmark": "V8-C3-MICRO",
    "task042_v9_frozen_error_localization": "V9-D0-D3",
    **{"task042_v10_"+name.lower(): "V10-"+name
       for name in ("A", "B1", "B0", "C", "E1", "E2", "VERIFY", "D1", "D2", "P4", "HEAD_CHECK", "D2_REPLAY")},
    "task042_v11_main": "V11-MAIN",
    "task042_v11_replay": "V11-REPLAY",
    "task042_v11_verify": "V11-VERIFY",
    "task042_v12_round": "V12-ROUND",
    "task042_v12_descent": "V12-DESCENT",
    "task042_v12_verify": "V12-VERIFY",
    **{"task042_v13_"+name.lower(): "V13-"+name
       for name in ("TANGENT", "RESPONSE", "COMPENSATE", "VERIFY")},
    **{"task042_v16_"+name.lower(): "V16-"+name
       for name in ("PREFLIGHT", "ZERO", "GPOLY", "GNN", "VERIFY")},
    **{"task042_v15_"+name.lower(): "V15-"+name
       for name in ("SETUP", "LOCAL_POLY", "LOCAL_NN", "UNION_POLY", "UNION_NN", "VERIFY")},
    **{"task042_v14_"+name.lower(): "V14-"+name
       for name in ("DECODER", "PROFILE", "VERIFY")},
}


def validate_task042_case(config):
    seed = tomllib.loads(
        (
            ROOT / "input/task39extra/original_13p5nm_p6h10_balanced_h6_p4_v5.dat"
        ).read_text()
    )
    for section in ("geometry", "materials", "incidence", "discretization", "boundary"):
        for key, expected in seed[section].items():
            actual = config[section][key]
            if isinstance(expected, list):
                actual = list(actual)
            if actual != expected:
                raise ValueError(
                    f"Task042 frozen {section}.{key}: {actual!r} != {expected!r}"
                )
    for section, key, value in (
        ("solver", "restart", 32),
        ("solver", "max_iterations", 2048),
        ("execution", "mpi_size", 1),
        ("execution", "warning_memory_gib", 12.0),
        ("execution", "terminate_memory_gib", 16.0),
        ("execution", "require_zero_swap", True),
        ("execution", "timeout_seconds", 10800),
        ("output", "results_root", "results/task042"),
    ):
        if config[section][key] != value:
            raise ValueError(f"Task042 requires {section}.{key}={value}")
    for key, value in seed["output"].items():
        actual = config["output"][key]
        if isinstance(value, list):
            actual = list(actual)
        if key != "results_root" and actual != value:
            raise ValueError(f"Task042 frozen output.{key}")
