"""Narrow readers for the saved E2 field packet schema."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def saved_solution_and_rhs_descriptors(
    packet: Mapping[str, Any],
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    """Use the actual top-level p6 solution and physical-RHS descriptors."""
    return packet["full_solution"], packet["physical_rhs"]
