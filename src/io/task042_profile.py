"""Explicit Task042 research profiles; historical inputs retain their contracts."""

from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parents[2]
TASK042_PROFILES = {
    "task042_shared_f1_reference_v1": "F1-reference",
    "task042_shared_f1_b0_v1": "F1-B0",
    "task042_shared_f2_teacher_v1": "F2-teacher",
    "task042_shared_f2_oracle_v1": "F2-oracle",
    "task042_shared_f3_train_v1": "F3-train",
    "task042_shared_f4_linear_v1": "F4-LIN",
    "task042_shared_f4_neural_v1": "F4-NN",
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
