"""Launch-scoped fail-closed cache guard; inert unless explicitly reviewed."""

import os

_MODE_ENV = "TASK40_EXACT_CACHE_REUSE_MODE"
_CONTRACT_ENV = "TASK40_EXACT_CACHE_REUSE_CONTRACT"
_CONTRACT_SHA_ENV = "TASK40_EXACT_CACHE_REUSE_CONTRACT_SHA256"

if os.environ.get(_MODE_ENV) is not None or any(
    os.environ.get(name) for name in (_CONTRACT_ENV, _CONTRACT_SHA_ENV)
):
    try:
        from task40_exact_cache_reuse import MODE, install_from_environment

        if os.environ.get(_MODE_ENV) != MODE:
            raise RuntimeError("invalid Gate-CD exact-cache reuse activation")
        install_from_environment()
    except BaseException as exc:
        # site.py suppresses ordinary exceptions raised by sitecustomize; an
        # explicit SystemExit makes a broken guard stop Python before user code.
        raise SystemExit(f"Gate-CD exact-cache guard refused Python startup: {exc}") from exc
