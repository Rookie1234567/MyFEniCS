"""Small regressions for the Task042 shared atomic metadata boundary."""

import json
from types import MappingProxyType

import numpy as np
import pytest

from src.runners.task042_shared import write_json


def test_nested_frozen_mapping_and_numpy_complex(tmp_path):
    path = tmp_path / "record.json"
    numeric = MappingProxyType({"value": np.float64(0.25),
                                "port": np.complex128(1 + 2j)})
    write_json(path, MappingProxyType({"numeric": numeric,
                                     "physical_identity": {"rows": np.int64(40)},
                                     "items": (MappingProxyType({"a": np.array([1j])}),)}))
    row = json.loads(path.read_text())
    assert row["numeric"] == {"value": 0.25, "port": {"real": 1., "imag": 2.}}
    assert row["physical_identity"] == {"rows": 40}
    assert row["items"][0]["a"] == [{"real": 0., "imag": 1.}]


def test_resource_cpu_keys_preserve_json_integer_index_semantics(tmp_path):
    path = tmp_path / "resource.json"
    write_json(path, {"cpu_busy_fractions": {0: 0.01, 1: 1.}})
    assert json.loads(path.read_text())["cpu_busy_fractions"] == {"0": 0.01, "1": 1.}
    with pytest.raises(ValueError, match="collision"):
        write_json(path, {0: 1, "0": 2})


@pytest.mark.parametrize("bad", [float("nan"), complex(0, float("inf")),
                                 np.zeros(4097), object()])
def test_encoding_failure_keeps_previous_numeric(tmp_path, bad):
    path = tmp_path / "record.json"
    write_json(path, {"numeric": {"loss": 1.}})
    before = path.read_bytes()
    with pytest.raises((ValueError, TypeError)):
        write_json(path, {"numeric": bad})
    assert path.read_bytes() == before


def test_interrupted_atomic_publish_keeps_previous_record(tmp_path, monkeypatch):
    path = tmp_path / "record.json"
    write_json(path, {"numeric": 1})
    before = path.read_bytes()
    def interrupted(*args):
        raise OSError("interrupted before publication")
    monkeypatch.setattr("src.runners.task042_shared.os.replace", interrupted)
    with pytest.raises(OSError):
        write_json(path, {"numeric": 2})
    assert path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [path]
