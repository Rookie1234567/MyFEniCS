"""Independent decision boundaries and saved-evidence checks; no PDE replay."""
import hashlib
from pathlib import Path

import numpy as np
import pytest

from benchmarks.check_p4_blr_v16 import _array, decide_s2, resource_scope


@pytest.mark.parametrize("peak,live,status", [
    (0.90, 0.95, "ADMIT_S3_PEAK_MEMORY_GAIN"),
    (1.05, 0.80, "ADMIT_S3_RESIDENT_MEMORY_GAIN_ONLY"),
    (0.9001, 0.8001, "STRONG_BUT_INSUFFICIENT_MEMORY_GAIN"),
    (1.0501, 0.70, "STRONG_BUT_INSUFFICIENT_MEMORY_GAIN"),
    (float("nan"), 0.70, "COMPARISON_INCONCLUSIVE"),
    (0.80, 0.0, "COMPARISON_INCONCLUSIVE"),
])
def test_frozen_memory_alternatives(peak, live, status):
    result = decide_s2(quality=True, comparison_valid=True, statistics_available=True,
                       compression_effect=True, r_peak=peak, r_live=live)
    assert result["status"] == status
    assert result["admit_s3"] == status.startswith("ADMIT_S3_")
    assert result["time_policy"] == "observe_only"


@pytest.mark.parametrize("changed,status", [
    ({"quality": False}, "BLR_ACTION_UNQUALIFIED"),
    ({"statistics_available": False}, "COMPRESSION_STATS_UNAVAILABLE"),
    ({"compression_effect": False}, "BLR_UNAVAILABLE_OR_NO_EFFECT"),
    ({"comparison_valid": False}, "COMPARISON_INCONCLUSIVE"),
])
def test_memory_gain_cannot_override_quality_or_evidence(changed, status):
    inputs = dict(quality=True, comparison_valid=True, statistics_available=True,
                  compression_effect=True, r_peak=0.5, r_live=0.5)
    inputs.update(changed)
    result = decide_s2(**inputs)
    assert result["status"] == status
    assert result["admit_s3"] is False


def test_saved_vector_hash_and_finiteness_are_checked(tmp_path):
    path = tmp_path / "vectors.npz"
    values = np.array([1 + 2j, 3 - 4j], dtype=np.complex128)
    np.savez(path, data=values)
    packet = {"arrays": {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()},
              "x": {"array_key": "data", "shape": [2], "dtype": "complex128"}}
    np.testing.assert_array_equal(_array(packet, "x", tmp_path), values)
    np.savez(path, data=2 * values)
    with pytest.raises(ValueError, match="hash mismatch"):
        _array(packet, "x", tmp_path)
    np.savez(path, data=np.array([complex("nan"), 0], dtype=np.complex128))
    packet["arrays"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="Non-finite"):
        _array(packet, "x", tmp_path)


def test_real_saved_q1_scope_without_rerunning_a_solver():
    baseline = Path(__file__).resolve().parents[2] / (
        "results/euv_grazing1_phi0/"
        "task39extra_v14_q1_full_direct__full3d_iterative__mpi1__Mna/"
        "20260913T115722.489252Z"
    )
    if not baseline.is_dir():
        pytest.skip("Local Q1 ignored evidence is unavailable")
    result = resource_scope(baseline, "v14")
    assert result["passed"], result["gates"]
    assert result["full_sample_count"] == 2091
    assert result["live_sample_count"] == 75
    assert result["full_rss_peak_bytes"] == 2825973760
    assert result["live_rss_peak_bytes"] == 2825973760
    assert result["full_pss_peak_bytes"] == 2795549696
