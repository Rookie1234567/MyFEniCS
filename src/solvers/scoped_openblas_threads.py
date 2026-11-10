"""Draft source helper for a verified, temporary OpenBLAS thread scope."""
from __future__ import annotations

from contextlib import contextmanager
import ctypes
import os
from pathlib import Path
from typing import Any, Iterator


class OpenBLASControlError(RuntimeError):
    """Thread change failed before the numerical callback was entered."""

    def __init__(self, message: str, *, serial_state_verified: bool):
        super().__init__(message)
        self.serial_state_verified = bool(serial_state_verified)


class OpenBLASRestoreError(RuntimeError):
    """The callback ran but OpenBLAS could not be verified at one thread."""


def _openblas_thread_api() -> tuple[Any, str, Any, Any]:
    """Resolve the unique already-loaded OpenBLAS library by real path."""
    mapped: set[str] = set()
    try:
        lines = Path("/proc/self/maps").read_text().splitlines()
    except OSError as exc:
        raise RuntimeError(f"cannot inspect loaded libraries for OpenBLAS: {exc}") from exc
    for line in lines:
        fields = line.split()
        if not fields:
            continue
        candidate = fields[-1]
        if "openblas" in Path(candidate).name.lower() and candidate.startswith("/"):
            mapped.add(os.path.realpath(candidate.removesuffix(" (deleted)")))
    if len(mapped) != 1:
        raise RuntimeError(
            f"expected exactly one loaded OpenBLAS shared library, found {sorted(mapped)}"
        )

    library_path = next(iter(mapped))
    library = ctypes.CDLL(library_path)
    try:
        get_threads = library.openblas_get_num_threads
        set_threads = library.openblas_set_num_threads
    except AttributeError as exc:
        raise RuntimeError(
            f"loaded OpenBLAS library lacks the required pthread thread API: {library_path}"
        ) from exc
    get_threads.argtypes = []
    get_threads.restype = ctypes.c_int
    set_threads.argtypes = [ctypes.c_int]
    set_threads.restype = None
    return library, library_path, get_threads, set_threads


def openblas_thread_snapshot() -> list[dict[str, Any]]:
    _library, library_path, get_threads, _set_threads = _openblas_thread_api()
    return [
        {
            "filepath": library_path,
            "internal_api": "openblas",
            "num_threads": int(get_threads()),
        }
    ]


def force_openblas_one() -> list[dict[str, Any]]:
    _library, library_path, get_threads, set_threads = _openblas_thread_api()
    set_threads(1)
    if int(get_threads()) != 1:
        raise OpenBLASRestoreError(
            f"OpenBLAS did not restore to one thread in {library_path}"
        )
    return openblas_thread_snapshot()


@contextmanager
def scoped_openblas_threads(threads: int) -> Iterator[dict[str, Any]]:
    """Run a callback at 8 threads, proving the 1->8->1 lifecycle."""
    if threads != 8:
        raise ValueError("the opt-in parallel scope only accepts exactly eight threads")
    try:
        _library, library_path, get_threads, set_threads = _openblas_thread_api()
    except Exception as exc:
        raise OpenBLASControlError(
            f"cannot resolve OpenBLAS controls before callback: {type(exc).__name__}: {exc}",
            serial_state_verified=False,
        ) from exc

    before = int(get_threads())
    if before != 1:
        try:
            set_threads(1)
            restored = int(get_threads()) == 1
        except Exception:
            restored = False
        raise OpenBLASControlError(
            f"OpenBLAS before scope was {before}, expected 1 in {library_path}",
            serial_state_verified=restored,
        )

    scope = {
        "filepath": library_path,
        "threads_before": before,
        "threads_during": None,
        "threads_after": None,
    }
    try:
        set_threads(8)
        during = int(get_threads())
        if during != 8:
            try:
                set_threads(1)
                restored = int(get_threads()) == 1
            except Exception:
                restored = False
            raise OpenBLASControlError(
                f"OpenBLAS readback was {during}, expected 8 in {library_path}",
                serial_state_verified=restored,
            )
        scope["threads_during"] = during
    except OpenBLASControlError:
        raise
    except Exception as exc:
        try:
            set_threads(1)
            restored = int(get_threads()) == 1
        except Exception:
            restored = False
        raise OpenBLASControlError(
            f"OpenBLAS failed before callback: {type(exc).__name__}: {exc}",
            serial_state_verified=restored,
        ) from exc

    try:
        yield scope
    finally:
        try:
            set_threads(1)
            after = int(get_threads())
        except Exception as exc:
            raise OpenBLASRestoreError(
                f"OpenBLAS restore/readback failed in {library_path}: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        scope["threads_after"] = after
        if after != 1:
            raise OpenBLASRestoreError(
                f"OpenBLAS restored to {after}, expected 1 in {library_path}"
            )
