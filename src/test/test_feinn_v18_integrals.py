import copy
import json
from pathlib import Path

import numpy as np
import pytest

from benchmarks.check_feinn_saved_integrals import REGIONS, verify
from src.solvers.feinn_saved_field_diagnostics import regional_statistics
from src.solvers.neural_fe_action_packet import array_hash


def fixture():
    volumes = np.array([1.0, 2.0, 3.0])
    energy = dict(
        before=np.array([2.0, 3.0]),
        delta=np.array([0.1, 0.2]),
        after=np.array([2.4, 3.6]),
        minus=np.array([1.8, 2.8]),
        reference=np.array([4.0, 5.0]),
        reference_total=np.array([8.0, 10.0]),
    )
    arrays = {
        "cell_volumes_nm3": volumes,
        **{"energy_" + key: value for key, value in energy.items()},
    }
    result = dict(
        status="SAVED_FIELD_INTEGRALS_COMPLETE",
        regions={},
        regions_are_overlapping_not_additive=True,
        pde_only_solve=False,
        production_initialization_allowed=False,
        official_candidate_results=False,
        pde_only_solver_qualified=False,
        Gram_factor_created=False,
        Maxwell_factor_created=False,
        A_actions=0,
        AH_actions=0,
        G_actions=0,
        Gsolve_count=0,
        total_volume_nm3=6.0,
        energies={key: value.tolist() for key, value in energy.items()},
        energy_terms={},
        ell_nm=5.0,
        k0_per_nm=2.0,
        G_norm_identity={},
        MPC={"before": 1e-16, "after": 1e-16},
        global_denominators={},
    )
    for i, name in enumerate(("E_L2", "scaled_curl_L2")):
        cross = (energy["after"][i] - energy["minus"][i]) / 2
        change = energy["after"][i] - energy["before"][i]
        update = energy["delta"][i]
        scale = max(energy["before"][i], energy["after"][i], abs(cross) + update)
        result["energy_terms"][name] = dict(
            before=energy["before"][i],
            after=energy["after"][i],
            cross=cross,
            change=change,
            update_energy=update,
            reconstructed_change=cross + update,
            operation_scale=scale,
            defect=abs(change - cross - update) / scale,
            reference_energy=energy["reference"][i],
        )
    original = {"rows": {}}
    for key, state in (("before", "M3600"), ("after", "Mfinal")):
        combined = energy[key][0] + 100 * energy[key][1]
        original["rows"][state] = {"field_G_squared": combined}
        result["G_norm_identity"][key] = dict(
            sparse_G_energy=combined, integrated_G_energy=combined, relative=0.0
        )
    for kind, key in (("scattered", "reference"), ("total", "reference_total")):
        result["global_denominators"][kind] = dict(
            reference_energy=energy[key].tolist(),
            actual_denominator=np.sqrt(energy[key]).tolist(),
            incident_floor=1e-12 * np.sqrt(6),
        )
    for name, cells in zip(REGIONS, ([0, 1], [1, 2], [0], [0, 2]), strict=True):
        cells = np.asarray(cells, np.int32)
        volume = volumes[cells].sum()
        ref = np.array([0.0, 0.5])
        row = dict(
            cells=len(cells),
            cell_ids_sha256=array_hash(cells),
            volume_nm3=volume,
            reference_energy=ref.tolist(),
            states={},
        )
        arrays["cells_" + name] = cells
        arrays[name + "_reference_energy"] = ref
        for state, key in (("M3600", "before"), ("Mfinal", "after")):
            value = energy[key] * volume / 6 * 0.9
            arrays[name + "_" + state + "_error_energy"] = value
            row["states"][state] = dict(
                **regional_statistics(value, ref, volume, 6, energy[key]),
                MPC_relative=1e-16,
            )
        row["increment"] = {
            key: (
                np.array(row["states"]["Mfinal"][key])
                - np.array(row["states"]["M3600"][key])
            ).tolist()
            for key in ("error_energy", "concentration")
        }
        result["regions"][name] = row
    return result, arrays, original


def test_overlapping_regions_and_near_zero_are_explicit():
    result, arrays, original = fixture()
    checked = verify(result, arrays, original)
    assert checked["status"] == "PASS" and checked["regions_not_summed"]
    assert (
        sum(row["volume_nm3"] for row in result["regions"].values())
        > result["total_volume_nm3"]
    )
    assert result["regions"]["air_notch"]["states"]["M3600"]["near_zero_reference"] == [
        True,
        False,
    ]


@pytest.mark.parametrize(
    "damage",
    [
        "key",
        "volume",
        "energy",
        "nonfinite",
        "cross",
        "G",
        "ids",
        "concentration",
        "floor",
        "policy",
    ],
)
def test_field_checker_rejects_corrupt_records(damage):
    result, arrays, original = fixture()
    result = copy.deepcopy(result)
    row = result["regions"]["air_notch"]
    if damage == "key":
        del result["regions"]["air_notch"]
    elif damage == "volume":
        row["volume_nm3"] += 1
    elif damage == "energy":
        row["states"]["M3600"]["error_energy"][0] += 1
    elif damage == "nonfinite":
        arrays["energy_before"][0] = np.nan
    elif damage == "cross":
        result["energy_terms"]["E_L2"]["cross"] += 1
    elif damage == "G":
        original["rows"]["M3600"]["field_G_squared"] *= 1.1
    elif damage == "ids":
        arrays["cells_air_notch"] = np.array([0, 0], np.int32)
    elif damage == "concentration":
        row["states"]["Mfinal"]["concentration"][0] += 1
    elif damage == "floor":
        row["states"]["M3600"]["actual_denominator"][0] *= 10
    else:
        result["official_candidate_results"] = True
    with pytest.raises(ValueError):
        verify(result, arrays, original)


def test_v18_stage_identity_whitelist_and_new_budget(monkeypatch):
    from src.runners import feinn_attribution_campaign as c
    from src.io.feinn_pilot import load_pilot

    for stage, (mode, _, _) in c.STAGES.items():
        if stage.startswith("v18_"):
            spec = load_pilot(Path("input/task042extra_feinn_5nm") / (stage + ".dat"))
            assert (
                spec.derived["environment_mode"] == mode
                and not spec.derived["pde_only_solve"]
            )
    actual = c.v18_index("e1_fe", "v18_saved_field_integrals")
    assert set(actual["files"]) == {"native"}
    campaign = json.loads(c.V18_DESIGN_RECORD.read_text())
    clock = json.loads((c.ROOT / campaign["batch_clock"]).read_text())
    monkeypatch.setattr("time.monotonic", lambda: clock["start_monotonic"] + 1000)
    ledger = c.v18_budget(
        [
            dict(
                path="/results/task42extra/task42extra_v18_saved_field_integrals_x/run_summary.json",
                seconds=50,
            ),
            dict(
                path="/results/task42extra/task42extra_v12_saved_field_integrals_x/run_summary.json",
                seconds=600,
            ),
        ]
    )
    assert (
        ledger["groups_used_seconds"]["B"] == 50
        and ledger["new_complete_wall_seconds"] == 1060
    )
    assert ledger["new_remaining_seconds"] == 15600 - 1060 - 600
