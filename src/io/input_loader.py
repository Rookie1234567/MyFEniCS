"""Byte-exact, stdlib-only loading of one Task38 ``.dat`` input."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping
import tomllib


class InputError(ValueError):
    """A user-facing Task38 input loading error."""


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


@dataclass(frozen=True)
class LoadedInput:
    """The one-read source payload and parsed TOML document."""

    source_path: Path
    raw_input_bytes: bytes
    input_sha256: str
    document: Mapping[str, Any]


def load_dat_input(path: str | Path) -> LoadedInput:
    """Read and parse exactly one UTF-8 Task38 ``.dat`` file."""

    source_path = Path(path)
    if source_path.suffix != ".dat":
        raise InputError(f"Task38 input must use the .dat suffix: {source_path}")

    try:
        raw_input_bytes = source_path.read_bytes()
    except OSError as exc:
        raise InputError(f"cannot read Task38 input {source_path}: {exc}") from exc

    input_sha256 = sha256(raw_input_bytes).hexdigest()
    try:
        text = raw_input_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InputError(
            f"Task38 input is not valid UTF-8: {source_path}: {exc}"
        ) from exc

    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise InputError(f"invalid TOML in {source_path}: {exc}") from exc

    return LoadedInput(
        source_path=source_path.resolve(),
        raw_input_bytes=raw_input_bytes,
        input_sha256=input_sha256,
        document=_freeze(document),
    )
