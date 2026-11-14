import csv
import json
from pathlib import Path

from src.postprocessing.diffraction_3d import _write_diffraction_orders_csv


FIXTURE = Path(__file__).with_name("fixtures") / "diffraction_orders_3d_csv_real_retry1.json"
FOURIER_FIELDS = {
    "bottom_e_fourier_projection_residual",
    "R_eh_fourier",
    "transmitted_amplitude_eh_fourier",
    "top_eh_fourier_fit_residual",
    "R_e_fourier",
    "reflected_amplitude_eh_fourier",
    "top_e_fourier_projection_residual",
    "transmitted_amplitude_e_fourier",
    "bottom_eh_fourier_fit_residual",
    "reflected_amplitude_e_fourier",
    "T_eh_fourier",
    "T_e_fourier",
}


def test_diffraction_csv_replays_saved_rows_with_late_fourier_fields(tmp_path):
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    rows = fixture["orders"]
    assert fixture["source_file"].endswith("p6_h10_direct_13p5_retry1/diffraction_orders_3d.json")
    assert len(fixture["source_sha256"]) == 64
    assert len(rows) == 2
    assert FOURIER_FIELDS.isdisjoint(rows[0])
    assert FOURIER_FIELDS.issubset(rows[1])

    output = tmp_path / "diffraction_orders_3d.csv"
    _write_diffraction_orders_csv(output, rows)

    with output.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        serialized = list(reader)
        assert reader.fieldnames == list(dict.fromkeys(key for row in rows for key in row))
    assert len(serialized) == len(rows)
    for key in FOURIER_FIELDS:
        assert serialized[0][key] == ""
        assert serialized[1][key] == str(rows[1][key])
