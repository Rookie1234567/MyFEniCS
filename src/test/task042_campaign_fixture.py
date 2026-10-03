"""Temporary one-run identity/clock/ledger, never a production campaign."""
import json
from types import SimpleNamespace

import pytest


@pytest.fixture
def isolated_v26_schema(monkeypatch, tmp_path):
    from src.io import joint_block_diagnostic as io
    from src.solvers import joint_block_window as window
    from src.solvers.exact_recycle_window import evaluate_window

    identity = {
        'action_sha256': '1' * 64, 'physical_sha256': '2' * 64,
        'states': [{'name': n} for n in io.NAMES],
        'joint_blocks': [5, 7], 'joint_rows': 3888,
    }
    plan = tmp_path / 'plan.json'
    plan.write_text(json.dumps(identity))
    monkeypatch.setattr(io, 'PLAN_PATH', plan)
    design = dict(geometry={'fixture': True}, incidence={}, finite_element={}, boundary={})
    material = SimpleNamespace(provenance={'material_table_id': 'SI_OPTICAL_CONSTANTS_USER_20260929_V1'})
    monkeypatch.setattr(io, 'plan_and_operator', lambda: (
        {'physical_model_sha256': identity['physical_sha256']}, design, material,
        {'packet': {'sha256': identity['action_sha256']}},
    ))
    for key, name in [('WINDOW_PATH', 'window.json'), ('LEDGER_PATH', 'ledger.json'),
                      ('JOURNAL_PATH', 'journal.jsonl')]:
        monkeypatch.setattr(window, key, tmp_path / name)
    monkeypatch.setattr(window, 'TMP', tmp_path)
    frozen = dict(start_utc='2026-01-01T00:00:00+00:00', start_monotonic=100.,
                  boot_id='fixture-boot', heavy_limit_seconds=6300, total_limit_seconds=7200)
    window.WINDOW_PATH.write_text(json.dumps(frozen))
    clock = {'utc': 1767225700., 'monotonic': 200.}
    monkeypatch.setattr(window, 'snapshot', lambda: evaluate_window(
        frozen, utc_seconds=clock['utc'], monotonic=clock['monotonic'], boot_id='fixture-boot'))
    book = window.ledger()
    return SimpleNamespace(window=window, clock=clock, book=book,
                           save=lambda: window.LEDGER_PATH.write_text(json.dumps(book)))
