from copy import deepcopy
import pytest


def test_all_v22_explicit_one_run_inputs():
    from src.io.fixed_phase_pilot import STAGES, ROOT
    from src.io.feinn_pilot import load_pilot

    for stage in STAGES:
        if not stage.startswith("v22_"):
            continue
        spec = load_pilot(ROOT / "input/task042extra_feinn_5nm" / f"{stage}.dat")
        assert spec.derived["campaign_version"] == 22
        assert spec.derived["neural_training_allowed"] is False
        assert spec.execution["math_threads"] == spec.execution["mpi_size"] == 1
        assert spec.execution["terminate_memory_gib"] == (
            2 if spec.derived["environment_mode"] == "pure" else 16
        )
        if spec.derived["role"] == "E4":
            assert spec.discretization["degree"] == 4


def test_wrong_material_or_design_rejected(tmp_path):
    from src.io.fixed_phase_pilot import ROOT
    from src.io.feinn_pilot import load_pilot
    from src.io.input_loader import InputError

    raw = (ROOT / "input/task042extra_feinn_5nm/v22_affine_saved.dat").read_text()
    raw = raw.replace(
        "b42aefb4028db68605f2349c3cfbc33c568924c6a2cdd382f6e04e2f9b6f2676", "0" * 64
    )
    path = tmp_path / "bad.dat"
    path.write_text(raw)
    with pytest.raises(InputError):
        load_pilot(path)


def test_shared_air_failure_cannot_hide_behind_role_pass():
    from benchmarks.reliable_port_checker import face_gates

    pair = dict(
        B_relative=[0.0] * 36,
        D_relative=[0.0] * 36,
        H_relative=[0.0] * 36,
        nonzero_actions=[[0.0, 0.0, 0.0]] * 3,
    )
    rows = [
        dict(
            role=r,
            physical_pair=deepcopy(pair),
            oracle_pair=deepcopy(pair),
            nonzero_port_load_original_recovery=0.0,
            omitted_real_facet_rejected=True,
            internal_coefficient_norm=1.0,
            negative_controls_complete=True,
            cutoff_witness_relative=0.0,
            ky=0.1,
            nonidentity_orientation_count=2,
            degree={"O3": 3, "E3": 3, "E4": 4, "O6_LOCAL_ONLY": 6}[r],
            phase=r in ("E3", "E4"),
            mode_keys=[
                [side, m, n, pol]
                for side in ("top", "bottom")
                for m in range(-1, 2)
                for n in range(-1, 2)
                for pol in ("s", "p")
            ],
        )
        for r in ("O3", "E3", "E4", "O6_LOCAL_ONLY")
    ]
    q = dict(
        roles=rows,
        air=[],
        small_sparse_LU_count=0,
        shared_qualified=True,
        stage_qualified=True,
    )
    result = face_gates(q)
    assert not result["shared"] and not result["whole"]
    assert all(result["roles"].values())
    q["roles"][0]["physical_pair"]["D_relative"][2] = 0.1
    assert not face_gates(q)["roles"]["O3"]
    q["roles"][1]["mode_keys"][0] = q["roles"][1]["mode_keys"][1]
    assert not face_gates(q)["roles"]["E3"]


def test_missing_and_duplicate_modes_cannot_be_partial_pass():
    from benchmarks.reliable_port_checker import face_gates

    with pytest.raises(ValueError):
        face_gates(
            dict(roles=[], air=[], small_sparse_LU_count=0, stage_qualified=True)
        )
