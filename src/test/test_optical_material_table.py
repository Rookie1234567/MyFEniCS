import json
import subprocess
from decimal import Decimal
from unittest.mock import patch

import numpy as np
import pytest
import tomllib

from src.common.optical_material_table import (
    CANONICAL_PATH,
    decimal_conversion,
    load_si_optical_constants,
)


@pytest.mark.parametrize("nominal", ["0.7", "2", "5", "13.5"])
def test_decimal_full_square_and_offline(nominal):
    with patch("socket.socket", side_effect=AssertionError("network prohibited")):
        selection = load_si_optical_constants(nominal)
    record = selection.provenance
    exact = decimal_conversion(record["delta"], record["beta"])
    assert exact == tuple(
        Decimal(value) for value in (*record["n_decimal"], *record["epsilon_decimal"])
    )
    assert selection.n.imag > 0 and selection.epsilon.imag > 0
    assert selection.epsilon == selection.n * selection.n
    assert selection.epsilon != abs(selection.n) ** 2
    assert selection.mu == 1 and record["air_n"] == [1.0, 0.0]
    assert (
        record["material_table_sha256"]
        and record["external_dataset_version"] == "not_provided"
    )


def test_only_explicit_point_alias():
    nominal = load_si_optical_constants("0.7")
    source = load_si_optical_constants("0.699999988")
    assert source.n == nominal.n == complex(0.999885140474, 0.00000432477054)
    assert nominal.provenance["source_wavelength_nm"] == "0.699999988"
    assert nominal.provenance["nominal_wavelength_nm"] == "0.7"
    for wavelength in ("0.699999989", "0.700000001", "1", "nan", "-1"):
        with pytest.raises(ValueError):
            load_si_optical_constants(wavelength)


def test_frozen_historical_values_and_blobs():
    table = json.loads(CANONICAL_PATH.read_text())
    for row in table["entries"]:
        for source in row["historical_evidence"]:
            identity = f"{source['commit']}:{source['path']}"
            assert (
                subprocess.check_output(
                    ["git", "rev-parse", identity], text=True
                ).strip()
                == source["blob"]
            )
            data = tomllib.loads(
                subprocess.check_output(["git", "show", identity]).decode()
            )
            selected = load_si_optical_constants(row["nominal_wavelength_nm"])
            for key in ("n_substrate", "n_grating"):
                np.testing.assert_array_equal(
                    data["materials"][key], [selected.n.real, selected.n.imag]
                )


def test_integrity_rejects_corruption(tmp_path):
    table = json.loads(CANONICAL_PATH.read_text())
    table["entries"][0]["beta"] = "-4.32477054E-06"
    path = tmp_path / "corrupted.json"
    path.write_text(json.dumps(table))
    with pytest.raises(ValueError, match="integrity"):
        load_si_optical_constants("0.7", path)
