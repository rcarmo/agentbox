"""Terminal helper utilities for attaching to container ttys and restoring terminal state.

Provides a single entrypoint `attach_command` which tries `subprocess.run`, then
`pty.spawn`, then an `execvp` handoff, restoring terminal state before/after.
"""
from __future__ import annotations

import os
import subprocess
import time
import pty
from typing import Sequence


def restore_terminal() -> None:
    """Attempt to restore common terminal modes and disable mouse reporting."""
    try:
        subprocess.run(["stty", "sane"], check=False)
    except Exception:
        pass
    try:
        subprocess.run(["tput", "rmcup"], check=False)
    except Exception:
        pass
    try:
        subprocess.run(["tput", "cnorm"], check=False)
    except Exception:
        pass
    try:
        # disable mouse reporting in case the remote enabled it
        subprocess.run(["bash", "-lc", "printf '\\e[?1000l'"], check=False)
    except Exception:
        pass


def attach_command(cmd: Sequence[str], delay: float = 1.5) -> bool:
    """Attach to an interactive command using several fallbacks.

    Returns True if the attach completed (exit code 0) or the process replaced
    the current process (execvp). Returns False on failure.
    """
    # allow caller to teardown UI/TTY first
    time.sleep(delay)
    restore_terminal()

    # 1) Try a simple subprocess.run (friendly for tests/mocks)
    try:
        result = subprocess.run(list(cmd), check=False)
        if result and getattr(result, "returncode", 0) == 0:
            return True
    except Exception:
        pass

    # 2) Try PTY spawn for interactive tty forwarding
    try:
        pty.spawn(list(cmd))
        return True
    except Exception:
        pass

    # 3) Try execvp handoff — this will not return on success
    try:
        os.execvp(cmd[0], list(cmd))
        return True
    except Exception:
        pass

    # final restore attempt
    restore_terminal()
    return False
