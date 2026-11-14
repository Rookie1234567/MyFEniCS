"""Opt-in stage allocation callback, outside all physical configuration hashes."""
from contextlib import contextmanager
from contextvars import ContextVar

_CALLBACK=ContextVar("myfenics_resource_admission",default=None)
_DISK_RESERVE_BYTES=ContextVar("myfenics_resource_disk_reserve_bytes",default=None)


@contextmanager
def resource_policy(callback, *, disk_reserve_bytes=None):
    if not callable(callback) or _CALLBACK.get() is not None:
        raise ValueError("one explicit callable resource policy is required")
    if disk_reserve_bytes is not None and (type(disk_reserve_bytes) is not int or disk_reserve_bytes < 0):
        raise ValueError("disk reserve must be a non-negative exact integer")
    token=_CALLBACK.set(callback)
    disk_token=_DISK_RESERVE_BYTES.set(disk_reserve_bytes)
    try:yield
    finally:
        _DISK_RESERVE_BYTES.reset(disk_token)
        _CALLBACK.reset(token)


def admit(stage,future_bytes,*,estimate_basis):
    callback=_CALLBACK.get()
    if callback is None:return None
    return callback(stage,int(future_bytes),estimate_basis=estimate_basis)


def active():
    return _CALLBACK.get() is not None


def disk_reserve_bytes(default=None):
    """Return an opt-in checkpoint disk floor, preserving the legacy default."""
    configured=_DISK_RESERVE_BYTES.get()
    return default if configured is None else configured
