"""Task38 input schema and pure input-loading primitives."""

from .input_loader import InputError, LoadedInput, load_dat_input
from .input_validation import (
    load_and_resolve,
    resolve_loaded_input,
)
from .resolved_config import (
    canonical_json_bytes,
    resolved_config_bytes,
    resolved_config_sha256,
    write_resolved_config,
)
from .run_specification import RunSpecification

__all__ = [
    "InputError",
    "LoadedInput",
    "RunSpecification",
    "canonical_json_bytes",
    "load_and_resolve",
    "load_dat_input",
    "resolve_loaded_input",
    "resolved_config_bytes",
    "resolved_config_sha256",
    "write_resolved_config",
]
