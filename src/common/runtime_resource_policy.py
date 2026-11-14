"""Opt-in stage allocation callback, outside all physical configuration hashes."""
from contextlib import contextmanager
from contextvars import ContextVar

_CALLBACK=ContextVar("myfenics_resource_admission",default=None)
_DISK_RESERVE_BYTES=ContextVar("myfenics_resource_disk_reserve_bytes",default=None)
_FACTOR_CHECKPOINT=ContextVar("myfenics_factor_checkpoint",default=True)
_MUMPS_COMPILER_COMMAND=ContextVar("myfenics_mumps_compiler_command",default=None)


@contextmanager
def resource_policy(callback, *, disk_reserve_bytes=None, factor_checkpoint=True,
                    mumps_compiler_command=None):
    if not callable(callback) or _CALLBACK.get() is not None:
        raise ValueError("one explicit callable resource policy is required")
    if disk_reserve_bytes is not None and (type(disk_reserve_bytes) is not int or disk_reserve_bytes < 0):
        raise ValueError("disk reserve must be a non-negative exact integer")
    if isinstance(mumps_compiler_command, (str, bytes)):
        raise ValueError("MUMPS compiler command must be an argv sequence")
    compiler_command=None if mumps_compiler_command is None else tuple(mumps_compiler_command)
    if compiler_command is not None and (not compiler_command or any(not isinstance(arg,str) or not arg for arg in compiler_command)):
        raise ValueError("MUMPS compiler command must be a non-empty string sequence")
    token=_CALLBACK.set(callback)
    disk_token=_DISK_RESERVE_BYTES.set(disk_reserve_bytes)
    checkpoint_token=_FACTOR_CHECKPOINT.set(bool(factor_checkpoint))
    compiler_token=_MUMPS_COMPILER_COMMAND.set(compiler_command)
    try:yield
    finally:
        _MUMPS_COMPILER_COMMAND.reset(compiler_token)
        _FACTOR_CHECKPOINT.reset(checkpoint_token)
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


def factor_checkpoint_enabled():
    return _FACTOR_CHECKPOINT.get()


def mumps_compiler_command(default=None):
    """Return an opt-in qualified MUMPS compiler argv for this run."""
    configured=_MUMPS_COMPILER_COMMAND.get()
    return default if configured is None else configured
