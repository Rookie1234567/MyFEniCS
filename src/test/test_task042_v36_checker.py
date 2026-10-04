"""Saved-cache checker with independent sparse synthetic arithmetic.

The frozen mode metadata is physical. The numeric functionals below are
synthetic, not a real FE boundary qualification or a forward solve.
"""

import hashlib
import json
from copy import deepcopy

import numpy as np
import pytest

from benchmarks.check_port_preparation import check_component
from src.io.port_preparation import PLAN, ROOT
from src.runners.task042_shared import write_json
from src.solvers.bounded_port_provider import content_hash
from src.solvers.port_component_study import array_file


def fixture_record(folder):
    from src.common.modes_3d import incident_power_3d
    from src.solvers.dtn_port_3d import _mode_power_at_boundary
    from src.solvers.fullspace_dtn_action import build_dynamic_mode_inventory
    from src.solvers.neural_fe_pilot import physical_config

    plan = json.loads(PLAN.read_text())
    design = json.loads((ROOT / plan["micro_design_path"]).read_text())
    cfg, _ = physical_config(design)
    modes, identities, digest = build_dynamic_mode_inventory(cfg)
    sparse = []
    rows = np.arange(9, dtype=np.int64)
    for i, identity in enumerate(identities):
        rng = np.random.default_rng(923611 + i)
        C = rng.normal(size=9) + 1j * rng.normal(size=9)
        D = rng.normal(size=9) + 1j * rng.normal(size=9)
        arrays = {
            "coupling_rows": rows,
            "coupling_values": C,
            "projection_rows": rows.copy(),
            "projection_values": D,
        }
        key = [
            i,
            identity["side"],
            identity["m"],
            identity["n"],
            identity["polarization"],
        ]
        sparse.append(
            {
                "index": i,
                "key": key,
                "identity": identity,
                "H": identity["projection_denominator"],
                "file": array_file(folder / f"mode_{i}.npz", **arrays),
                "numeric_sha256": content_hash(arrays),
            }
        )
    manifest = folder / "surface.json"
    write_json(
        manifest,
        {
            "schema": "bounded-port.surface.v1",
            "modes": sparse,
            "global_rows": 34050,
            "ownership_range": [0, 34050],
            "slave_rows": [],
            "physical_sha256": plan["micro_physical_sha256"],
            "mode_manifest_sha256": digest,
        },
    )

    def apply(x, adjoint=False):
        out = np.zeros(34050, complex)
        for row in sparse:
            with np.load(row["file"]["path"], allow_pickle=False) as f:
                C, D = f["coupling_values"], f["projection_values"]
            out[:9] += (
                D.conj() * np.vdot(C, x[:9]) if adjoint else C * np.dot(D, x[:9])
            ) / row["H"]
        return out

    weights = np.array(
        [_mode_power_at_boundary(m, cfg, 1.0) / incident_power_3d(cfg) for m in modes]
    )
    arrays = {"zero_forward": np.zeros(34050, complex)}
    for seed in (423611, 423613):
        rng = np.random.default_rng(seed)
        x = rng.normal(size=34050) + 1j * rng.normal(size=34050)
        y = rng.normal(size=34050) + 1j * rng.normal(size=34050)
        alpha = rng.normal(size=40) + 1j * rng.normal(size=40)
        recovered, modal = [], np.zeros(34050, complex)
        for row, a in zip(sparse, alpha, strict=True):
            with np.load(row["file"]["path"], allow_pickle=False) as f:
                recovered.append(np.dot(f["projection_values"], x[:9]) / row["H"])
                modal[:9] += f["coupling_values"] * a
        recovered = np.array(recovered)
        s = str(seed)
        arrays.update(
            {
                "x_" + s: x,
                "y_" + s: y,
                "alpha_" + s: alpha,
                "scaled_forward_" + s: (0.37 - 0.91j) * apply(x),
            }
        )
        for partner in ("old", "new"):
            arrays.update(
                {
                    partner + "_forward_" + s: apply(x),
                    partner + "_adjoint_" + s: apply(y, True),
                    partner + "_amplitudes_" + s: recovered,
                    partner + "_modal_rhs_" + s: modal,
                    partner + "_power_" + s: weights * abs(recovered) ** 2,
                    "unit_" + partner + "_power_" + s: weights,
                }
            )
    record = {
        "surface_manifest": {
            "path": str(manifest),
            "sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        },
        "mode_manifest_sha256": digest,
        "physical_sha256": plan["micro_physical_sha256"],
        "design_sha256": plan["micro_design_sha256"],
        "volume_actions": 0,
        "new_LU": 0,
        "new_QR": 0,
        "KSP": 0,
        "reference_read": False,
        "seven_block_factors_read": False,
        "seeds": [423611, 423613],
        "FE_storage": 34050,
        "quadrature": 15,
        "source_identity": "independent synthetic cache fixture",
        "numeric_witness": array_file(folder / "witness.npz", **arrays),
        "incident_power": incident_power_3d(cfg),
        "provider_stats": {
            "cache_peak_bytes": 880,
            "lease_peak_bytes": 880,
            "created_live_peak": 2,
            "active_batches_peak": 1,
            "evictions": 38,
        },
        "cache_empty_after": True,
    }
    return record, arrays


def test_saved_checker_recomputes_all_outputs_and_rejects_consistent_bad_adjoint_and_inventory(
    tmp_path,
):
    record, arrays = fixture_record(tmp_path)
    checked = check_component(record, tmp_path)
    assert checked["status"] == "PORT_COMPONENT_CACHE_CHECKED"
    # A falsified saved status is never an acceptance source.
    wrong = deepcopy(record)
    wrong["status"] = "PASSED"
    bad = dict(arrays)
    bad["new_adjoint_423611"] = arrays["new_adjoint_423611"].conj()
    wrong["numeric_witness"] = array_file(tmp_path / "bad.npz", **bad)
    with pytest.raises(ValueError, match="saved boundary component gate"):
        check_component(wrong, tmp_path)
    bad = dict(arrays)
    bad.pop("old_amplitudes_423613")
    wrong["numeric_witness"] = array_file(tmp_path / "missing.npz", **bad)
    with pytest.raises(ValueError, match="witness inventory"):
        check_component(wrong, tmp_path)
    wrong = deepcopy(record)
    wrong["numeric_witness"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="container hash"):
        check_component(wrong, tmp_path)
    wrong = deepcopy(record)
    wrong["mode_manifest_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="frozen micro"):
        check_component(wrong, tmp_path)
