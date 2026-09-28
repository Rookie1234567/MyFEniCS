"""Actual frozen mode inventory serialization; no mesh/forms/JIT/factor."""

import json

from src.io import load_and_resolve
from src.io.input_validation import simulation_config_3d_from_normalized
from src.runners.task042_shared import write_json
from src.solvers.fullspace_dtn_action import build_dynamic_mode_inventory


def test_all_eighty_actual_mode_rows_are_serializable_without_losing_phase(tmp_path):
    specification = load_and_resolve(
        "input/task042_neural_coarse_inverse/f1_b0_shared_retry3.dat"
    )
    cfg = simulation_config_3d_from_normalized(specification.as_jsonable())
    modes, rows, sha = build_dynamic_mode_inventory(cfg)
    assert len(modes) == len(rows) == 80 and len(sha) == 64
    path = tmp_path / "mode_inventory.json"
    write_json(path, {"mode_rows": rows, "mode_sha256": sha})
    observed = json.loads(path.read_text())
    assert observed["mode_sha256"] == sha
    count = 0
    for raw, restored in zip(rows, observed["mode_rows"], strict=True):
        for key, value in raw.items():
            if isinstance(value, complex):
                assert complex(restored[key]["real"], restored[key]["imag"]) == value
                count += 1
    assert count > 0
