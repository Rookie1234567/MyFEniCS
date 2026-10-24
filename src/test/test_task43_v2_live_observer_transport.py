import json
import pickle
from types import MappingProxyType

import numpy as np
import pytest

from benchmarks.task43_hp_adaptivity import h100_anchor
from src.runners.p6_condensed_direct import _atomic_json


def test_nested_readonly_observer_result_is_pickle_and_json_transportable():
    payload = MappingProxyType(
        {
            "before_port_metrics": MappingProxyType(
                {
                    "R00_by_polarization": MappingProxyType({"s": 0.25}),
                    "phase": 1.0 + 2.0j,
                }
            ),
            "before_condensed_residual": MappingProxyType(
                {"groups": MappingProxyType({"trace": np.array([1.0 + 0.5j])})}
            ),
        }
    )

    with pytest.raises(TypeError, match="cannot pickle 'mappingproxy' object"):
        pickle.dumps(payload)

    transport_payload = h100_anchor._plain_nested_containers(payload)
    received = pickle.loads(pickle.dumps(transport_payload))
    assert type(received) is dict
    assert type(received["before_port_metrics"]) is dict
    assert type(received["before_port_metrics"]["R00_by_polarization"]) is dict
    np.testing.assert_array_equal(
        received["before_condensed_residual"]["groups"]["trace"],
        np.array([1.0 + 0.5j]),
    )

    json_payload = json.loads(
        json.dumps(transport_payload, default=h100_anchor._json_default)
    )
    assert json_payload["before_port_metrics"]["phase"] == [1.0, 2.0]
    assert json_payload["before_condensed_residual"]["groups"]["trace"] == [[1.0, 0.5]]


def test_native_summary_atomic_json_handles_readonly_numeric_payload(tmp_path):
    values = np.array([1.0 + 0.5j], dtype=np.complex128)
    values.setflags(write=False)
    summary = MappingProxyType(
        {
            "factor": MappingProxyType(
                {
                    "mumps_info": MappingProxyType({"factor_flops": 12.0}),
                    "complex_probe": np.complex128(2.0 - 3.0j),
                }
            ),
            "residual": MappingProxyType({"vector": values}),
        }
    )
    path = tmp_path / "native_summary.json"

    _atomic_json(path, summary)

    result = json.loads(path.read_text(encoding="utf-8"))
    assert result["factor"]["mumps_info"]["factor_flops"] == 12.0
    assert result["factor"]["complex_probe"] == [2.0, -3.0]
    assert result["residual"]["vector"] == {
        "array_omitted": True,
        "dtype": "complex128",
        "shape": [1],
        "finite": True,
    }
