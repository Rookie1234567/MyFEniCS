"""Opt-in stage allocation callback, outside all physical configuration hashes."""
from contextlib import contextmanager
from contextvars import ContextVar

_CALLBACK=ContextVar("myfenics_resource_admission",default=None)


@contextmanager
def resource_policy(callback):
    if not callable(callback) or _CALLBACK.get() is not None:
        raise ValueError("one explicit callable resource policy is required")
    token=_CALLBACK.set(callback)
    try:yield
    finally:_CALLBACK.reset(token)


def admit(stage,future_bytes,*,estimate_basis):
    callback=_CALLBACK.get()
    if callback is None:return None
    return callback(stage,int(future_bytes),estimate_basis=estimate_basis)


def active():
    return _CALLBACK.get() is not None
