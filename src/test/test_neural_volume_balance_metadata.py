"""A read-only FE audit must survive JSON serialization unchanged."""

import json
from types import MappingProxyType

from src.solvers.neural_volume_balance import plain_mapping


def test_nested_readonly_audit_serializes_without_mutating_original():
    original = MappingProxyType(
        {"components": MappingProxyType({"curl": MappingProxyType({"apply_count": 3})})}
    )
    actual = plain_mapping(original)
    assert json.loads(json.dumps(actual)) == {
        "components": {"curl": {"apply_count": 3}}
    }
    assert isinstance(original["components"]["curl"], MappingProxyType)
