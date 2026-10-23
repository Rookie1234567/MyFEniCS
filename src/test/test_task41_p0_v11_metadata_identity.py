from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from src.runners.task41_p0_v4_volume_only_audit import (
    _task41_p0_v11_metadata_accounting_path_matches,
)


def test_v11_attempt02_metadata_path_binds_real_accounting_ledger() -> None:
    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "task41_p0_v11_metadata_attempt02_identity.json"
    )
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    assert fixture["_fixture_source"]["sha256"] == (
        "332baa3a5253a8322b56615c7fe087e401f909c3c889fa048fccc3f9f2b9fcd3"
    )
    report = fixture["metadata_report"]
    state = report["initial_fixed_window_state"]
    metadata = report["selected_trace_star_metadata_only"]
    accounting_path = Path(state["path"])
    window_json_path = accounting_path.with_name("execution_window_saved_diagnostics_6h.json")
    window = SimpleNamespace(
        path=window_json_path,
        accounting_path=accounting_path,
    )

    assert _task41_p0_v11_metadata_accounting_path_matches(state, window)
    assert not _task41_p0_v11_metadata_accounting_path_matches(
        state,
        SimpleNamespace(accounting_path=window_json_path),
    )
    assert [
        cell["cell_index"] for cell in metadata["selected_cells"]
    ] == metadata["incident_cell_order"]
