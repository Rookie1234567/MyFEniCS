from __future__ import annotations

import pytest

from src.runners import fine_reference_preflight
from src.runners.physical_p4_schur_v14 import _abi_facts


def test_abi_facts_keeps_legacy_default_and_rejects_non_v10_profile(monkeypatch):
    monkeypatch.setattr(fine_reference_preflight, "qualified_abi", lambda: {"legacy": True})
    assert _abi_facts() == {"legacy": True}
    with pytest.raises(RuntimeError, match="only the exact p4-control or p6-candidate profile"):
        _abi_facts(profile_identity="legacy_profile")
