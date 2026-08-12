"""Immutable resolved Task38 input data."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping


def freeze(value: Any) -> Any:
    """Recursively freeze mappings and sequences used by a run specification."""

    if isinstance(value, Mapping):
        return MappingProxyType({key: freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze(item) for item in value)
    return value


def thaw(value: Any) -> Any:
    """Return a detached JSON-friendly container copy."""

    if isinstance(value, Mapping):
        return {str(key): thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw(item) for item in value]
    return value


@dataclass(frozen=True)
class RunSpecification:
    """A fully resolved one-run public configuration and its provenance."""

    identity: Mapping[str, Any]
    geometry: Mapping[str, Any]
    materials: Mapping[str, Any]
    incidence: Mapping[str, Any]
    discretization: Mapping[str, Any]
    boundary: Mapping[str, Any]
    method: Mapping[str, Any]
    solver: Mapping[str, Any]
    execution: Mapping[str, Any]
    output: Mapping[str, Any]
    derived: Mapping[str, Any]
    source_path: Path
    raw_input_bytes: bytes
    input_sha256: str
    physical_model_sha256: str
    expected_output_parent: Path

    def __post_init__(self) -> None:
        for name in (
            "identity",
            "geometry",
            "materials",
            "incidence",
            "discretization",
            "boundary",
            "method",
            "solver",
            "execution",
            "output",
            "derived",
        ):
            object.__setattr__(self, name, freeze(getattr(self, name)))
        object.__setattr__(self, "source_path", Path(self.source_path))
        object.__setattr__(
            self, "expected_output_parent", Path(self.expected_output_parent)
        )

    def as_jsonable(self) -> dict[str, Any]:
        """Return a detached JSON-friendly resolved-config snapshot."""

        result = {"schema_version": 1}
        result.update(thaw(self.identity))
        for section in (
            "geometry",
            "materials",
            "incidence",
            "discretization",
            "boundary",
            "method",
            "solver",
            "execution",
            "output",
        ):
            result[section] = thaw(getattr(self, section))
        result["derived"] = thaw(self.derived)
        result["provenance"] = {
            "source_path": str(self.source_path),
            "input_sha256": self.input_sha256,
            "physical_model_sha256": self.physical_model_sha256,
            "expected_output_parent": str(self.expected_output_parent),
        }
        return result
