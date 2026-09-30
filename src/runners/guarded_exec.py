"""Linux-only opt-in exec: kill this worker if its exact supervisor dies."""

import ctypes
import os
from pathlib import Path
import signal
import sys


def ticks(pid):
    return int((Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split())[19])


def main():
    parent, start = int(sys.argv[1]), int(sys.argv[2])
    command = sys.argv[3:]
    if not command:
        raise ValueError("guarded exec requires a command")
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "PR_SET_PDEATHSIG denied")
    # Close the race between Popen and setting PDEATHSIG.
    if os.getppid() != parent or ticks(parent) != start:
        os.kill(os.getpid(), signal.SIGKILL)
    os.environ["TASK42EXTRA_PARENT_DEATH_GUARD"] = f"{parent}:{start}:SIGKILL"
    os.execvpe(command[0], command, os.environ)


if __name__ == "__main__":
    main()
