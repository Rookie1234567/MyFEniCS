from __future__ import annotations

import argparse

import pytest

from benchmarks.run_task034_wsl_qualification import (
    DEFAULT_MPI_SIZES,
    _parse_args,
    _parse_optional_probe_sizes,
    _parse_required_probe_sizes,
    _physical_core_inventory,
    _validate_probe_sizes,
)


def test_ordinary_qualification_default_remains_mpi1_mpi2_mpi4() -> None:
    args = _parse_args([])
    assert args.mpi_sizes == DEFAULT_MPI_SIZES == (1, 2, 4)
    assert args.distributed_solver_sizes == ()
    assert args.exploratory_mpi_sizes == ()
    assert not args.solver_microfixture


def test_extended_scope_labels_mpi32_exploratory() -> None:
    args = _parse_args(
        [
            "--mpi-sizes",
            "1,2,4,8,16,32",
            "--distributed-solver-sizes",
            "8,16,32",
            "--exploratory-mpi-sizes",
            "32",
        ]
    )
    assert args.mpi_sizes == (1, 2, 4, 8, 16, 32)
    assert args.distributed_solver_sizes == (8, 16, 32)
    assert args.exploratory_mpi_sizes == (32,)
    assert _validate_probe_sizes(
        args.mpi_sizes,
        args.distributed_solver_sizes,
        args.exploratory_mpi_sizes,
    ) == (
        args.mpi_sizes,
        args.distributed_solver_sizes,
        args.exploratory_mpi_sizes,
    )


@pytest.mark.parametrize("value", ["", "0", "1,1", "one,2", "1,-2"])
def test_required_probe_sizes_fail_closed(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        _parse_required_probe_sizes(value)


def test_optional_probe_sizes_accept_empty_only_as_no_opt_in() -> None:
    assert _parse_optional_probe_sizes("") == ()
    assert _parse_optional_probe_sizes("8,16") == (8, 16)


@pytest.mark.parametrize(
    ("mpi_sizes", "solver_sizes", "exploratory_sizes"),
    [
        ((1, 2, 8), (), ()),
        ((1, 2, 4, 8), (16,), ()),
        ((1, 2, 4, 8), (), (16,)),
        ((1, 2, 4, 4), (), ()),
    ],
)
def test_probe_scope_validation_rejects_incomplete_or_ambiguous_sets(
    mpi_sizes: tuple[int, ...],
    solver_sizes: tuple[int, ...],
    exploratory_sizes: tuple[int, ...],
) -> None:
    with pytest.raises(ValueError):
        _validate_probe_sizes(mpi_sizes, solver_sizes, exploratory_sizes)


def test_physical_core_inventory_is_readable_without_assuming_host_size() -> None:
    inventory = _physical_core_inventory()
    assert inventory["pass"], inventory
    assert inventory["available_physical_core_count"] > 0
    assert (
        inventory["allowed_logical_cpu_count"]
        >= inventory["available_physical_core_count"]
    )
