from __future__ import annotations

from pathlib import Path

from src import main as main_module
from src.io import load_and_resolve
from src.io.preset_migration import MIGRATED_PRESET_DATS


ROOT = Path(__file__).resolve().parents[2]
RETAINED = {
    "3d_stage4b_demo_direct_h5",
    "3d_stage4b_demo_direct_h3",
    "3d_stage4b_demo_mumps_ooc",
    "3d_stage4b_demo_mumps_blr",
    "3d_target_grating_direct_h5",
    "3d_target_grating_direct_h3",
}


def test_listing_has_11_dat_aliases_and_6_retained_presets():
    names = set(main_module.available_preset_names())
    assert len(names) == 17
    assert set(MIGRATED_PRESET_DATS) <= names
    assert set(main_module.PRESETS_3D) == RETAINED
    assert set(main_module.PRESET_INFO) == RETAINED

    listing = main_module.format_preset_listing(verbose=True).splitlines()
    assert len(listing) == 17
    migrated_rows = [row for row in listing if "status=migrated_to_dat" in row]
    assert len(migrated_rows) == 11
    assert all("dat=" in row and "geometry=" not in row for row in migrated_rows)
    assert sum("geometry=" in row for row in listing) == 6


def test_migrated_aliases_resolve_through_the_public_dat_entrypoint():
    for name, relative_path in MIGRATED_PRESET_DATS.items():
        dimension, args = main_module.preset_cli_args(name)
        assert dimension == "dat"
        assert args == [relative_path]
        assert main_module.main(["--preset", name, "--validate-only"]) == 0


def test_migrated_alias_rejects_overrides_and_no_args_never_dispatches(capsys):
    name = next(iter(MIGRATED_PRESET_DATS))
    assert main_module.main(["--preset", name, "--results-root", "other"]) == 2
    assert main_module.main([]) == 2
    captured = capsys.readouterr()
    assert "no longer selects an implicit preset" in captured.err
    assert "Usage: python scripts/run_case.py" in captured.err


def test_main_rejects_direct_runner_facades_without_dispatch(monkeypatch, capsys):
    from src.runners import run_3d_cases, run_cases

    calls = []
    monkeypatch.setattr(run_cases, "main", lambda args: calls.append(("2d", args)))
    monkeypatch.setattr(run_3d_cases, "main", lambda args: calls.append(("3d", args)))

    for args in (["2d"], ["3d", "--help"], ["--unknown"]):
        assert main_module.main(list(args)) == 2

    assert calls == []
    assert "Deprecated direct runner arguments" in capsys.readouterr().err


def test_retained_presets_keep_the_legacy_stage4_parser():
    for name in RETAINED:
        dimension, args = main_module.preset_cli_args(name)
        assert dimension == "3d"
        assert args[args.index("--stage-case") + 1] == "stage4_block_grating"
        assert main_module.PRESETS_3D[name].stage_case == "stage4_block_grating"


def test_retained_and_migrated_names_are_not_implicit_source_symbols():
    text = Path(main_module.__file__).read_text(encoding="utf-8")
    assert "ACTIVE_PYCHARM_PRESET" not in text
    assert "ACTIVE_2D_INPUT_GROUP" not in text
    assert "ACTIVE_3D_INPUT_GROUP" not in text
    assert "USE_PYCHARM_SETTINGS_WHEN_NO_ARGS" not in text


def test_retained_preset_runner_replay_still_accepts_all_six(tmp_path, monkeypatch):
    from src.runners import run_3d_cases

    captured = []

    def fake_run(cfg, out_dir):
        captured.append((cfg, out_dir))
        return {"case_name": cfg.case_name, "out_dir": str(out_dir)}

    monkeypatch.setattr(run_3d_cases, "_run_stage_config", fake_run)
    for name in sorted(RETAINED):
        _, args = main_module.preset_cli_args(name)
        run_3d_cases.main([*args, "--results-root", str(tmp_path / name)])
    assert len(captured) == 6


def test_main_list_presets_is_non_running_and_deterministic(capsys):
    assert main_module.main(["--list-presets"]) == 0
    names = capsys.readouterr().out.splitlines()
    assert names == sorted(names)
    assert len(names) == 17


def test_benchmark_stage1_mpi2_dat_preserves_physics_and_changes_only_identity():
    mpi1 = load_and_resolve(ROOT / "input/smoke/3d_stage1_airbox_smoke.dat")
    mpi2 = load_and_resolve(ROOT / "input/official/stage1_airbox_smoke_mpi2.dat")

    assert mpi1.physical_model_sha256 == mpi2.physical_model_sha256
    assert mpi1.identity["model_id"] != mpi2.identity["model_id"]
    assert mpi1.identity["run_id"] != mpi2.identity["run_id"]
    assert mpi1.execution["mpi_size"] == 1
    assert mpi2.execution["mpi_size"] == 2
