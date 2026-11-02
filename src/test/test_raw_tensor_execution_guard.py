from types import SimpleNamespace

import pytest

from src.solvers.hcurl_assembly_time_condensation import _global_raw_tensor_cache


@pytest.mark.parametrize("size,evaluator", [(2, None), (1, object())])
def test_exec_cache_rejects_mpi_or_alternate_evaluator_before_collectives(
    size, evaluator
):
    # This object deliberately has no MPI collective methods: rejection must
    # precede all mesh communication and kernel execution.
    comm = SimpleNamespace(size=size)
    with pytest.raises(ValueError, match="MPI1 and the original exact evaluator"):
        _global_raw_tensor_cache(
            comm,
            {},
            {},
            raw_tensor_evaluator=evaluator,
            raw_tensor_execution_config={"cpus": [0]},
        )
