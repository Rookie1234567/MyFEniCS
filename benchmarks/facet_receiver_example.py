"""Runnable minimal consumer of the frozen receiver's existing contraction.

Only FacetPolynomial is extracted from a hash-bound read-only Git source.
No BoundaryLayout, owner, communication, MPC, volume engine or runner is copied.
"""

import ast
from pathlib import Path
from types import MappingProxyType

import numpy as np
from numpy.polynomial.legendre import legvander

from src.solvers.strict_port_admission import digest_file

RECEIVER_SHA = "81b0f3cf42e01402a650555f92db1425d92dc9cd658bfd4c0a172be743cf159f"


def receiver_class(path):
    path = Path(path)
    if digest_file(path) != RECEIVER_SHA:
        raise ValueError("FROZEN_RECEIVER_SOURCE_MISMATCH")
    tree = ast.parse(path.read_text())
    nodes = [
        n
        for n in tree.body
        if isinstance(n, ast.ClassDef) and n.name == "FacetPolynomial"
    ]
    if len(nodes) != 1:
        raise ValueError("UNIQUE_RECEIVER_FACET_CLASS_REQUIRED")
    scope = dict(np=np, legvander=legvander, MappingProxyType=MappingProxyType)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), scope)
    return scope["FacetPolynomial"]


def consume(polynomial, side, k, J, origin, *, implementation, expected):
    if implementation == "q60":
        # The ordinary receiver path is exactly preserved, without importing
        # the analytic provider and its scipy dependencies in this process.
        return polynomial.integral(side, k, J, origin, 60)
    if implementation == "analytic":
        from src.solvers.interval_facet_moments import IntervalFacetAdapter

        return IntervalFacetAdapter(polynomial, lambda *_: expected).integral(
            side, k, J, origin, 60
        )
    raise ValueError("EXPLICIT_ANALYTIC_OR_Q60_SELECTION_REQUIRED")
