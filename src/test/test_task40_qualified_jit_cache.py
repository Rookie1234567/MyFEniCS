"""Task40's qualified parent JIT cache binding stays explicit and scoped."""

from pathlib import Path

import pytest

from src.io.physical_intermediate_profile import (
    PROJECTION_LAYOUT_V31_PROFILE,
    TASK40_0P7NM_PROFILE,
    TASK40_CANONICAL_PARENT_WORKTREE,
    TASK40_QUALIFIED_JIT_CACHE_SOURCE,
    V23_QUALIFIED_JIT_CACHE_SOURCE,
    profile_facts,
)


def test_task40_binds_the_canonical_parent_cache_without_changing_v31():
    task40_resources = profile_facts(TASK40_0P7NM_PROFILE)["resources"]
    v31_resources = profile_facts(PROJECTION_LAYOUT_V31_PROFILE)["resources"]
    source = Path(task40_resources["qualified_jit_cache_source"])

    assert source.is_absolute()
    assert task40_resources["qualified_jit_cache_source"] == (
        TASK40_CANONICAL_PARENT_WORKTREE + "/" + V23_QUALIFIED_JIT_CACHE_SOURCE
    )
    assert task40_resources["qualified_jit_cache_source"] == (
        TASK40_QUALIFIED_JIT_CACHE_SOURCE
    )
    assert "Task39extra canonical worktree" in task40_resources[
        "qualified_jit_cache_origin"
    ]
    assert v31_resources["qualified_jit_cache_source"] == (
        V23_QUALIFIED_JIT_CACHE_SOURCE
    )

    if not source.is_dir():
        pytest.skip("the explicitly bound Task39 artifact is not provisioned here")
    assert any(source.iterdir())
