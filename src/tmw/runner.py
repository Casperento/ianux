"""SessionRunner — run commands inside a detached tmux session.

Models the tmrun() bash function: create a new detached session and pipe
each provided command into it sequentially.  One window, one pane; commands
run one after the other as if typed by a user.  No pane splitting.

When *RunConfig.kill* is True the runner additionally:
  1. Appends a sentinel ``echo`` after all user commands.
  2. Forks a background daemon (double-fork, POSIX) that polls
     ``capture-pane`` every *_POLL_INTERVAL_S* seconds until the sentinel
     string appears in the pane output — proof that every preceding command
     has finished (shells execute queued input in order).
  3. The daemon strips the sentinel line from the captured text, writes the
     result to *RunConfig.output* or ``/tmp/<session_name>.capture-pane``,
     kills the session, and appends a ``[DONE]`` line to the sidecar log
     at ``/tmp/<session_name>.monitor.log``.  Any error is written to that
     same log as ``[ERROR]``.
  4. The foreground process returns immediately after spawning the daemon,
     so the user's shell prompt is not blocked.

Why a sentinel instead of polling pane_current_command?
  ``send-keys`` returns as soon as tmux acknowledges the keystroke, not when
  the shell begins executing it.  If the very first poll fires before the
  shell starts the first command, ``pane_current_command`` still shows the
  shell name and the runner would return immediately — before any work ran.
  The sentinel is queued *after* all user commands in the same input stream,
  so its appearance in the scrollback is an unambiguous completion signal
  that eliminates the race entirely.

Why exact-line matching for the sentinel?
  When ``send_keys`` writes keystrokes, the PTY driver echoes each character
  immediately into the pane — before the shell executes anything.  The echoed
  command text ``echo __tmw_job_done__`` therefore appears in the
  pane the instant ``send_keys`` returns and *contains* the sentinel as a
  substring.  A naïve ``_SENTINEL in raw`` check would match this echo and
  return prematurely, killing the session before any user command runs.

  Exact-line matching (``.strip() == _SENTINEL``) distinguishes the two:

  * ``echo __tmw_job_done__``  — command echo; **not** a match
  * ``__tmw_job_done__``        — actual echo output; **match**
"""

import os
import sys
import time
from pathlib import Path
from typing import Callable

from .config import RunConfig
from .exceptions import AppError
from .tmux import TmuxClient

# Window/pane target for the sole window+pane created by `tmux new-session -d`.
_DEFAULT_WINDOW = "0"
_DEFAULT_PANE = "0"

# Sentinel written to the pane after all user commands to signal completion.
# Distinctive enough that it won't appear in normal command output.
_SENTINEL = "__tmw_job_done__"

_POLL_INTERVAL_S: float = 2.0
_POLL_TIMEOUT_S: float = 3600.0  # 1-hour ceiling


class SessionRunner:
    """Handles the 'run' subcommand: pipe commands into a detached tmux session."""

    def __init__(self, client: TmuxClient) -> None:
        self._client = client

    def run(self, config: RunConfig) -> int:
        """Create a detached session, send every command, print a summary.

        When *config.kill* is True, queue a sentinel after the user commands
        and spawn a background daemon that waits for completion, captures the
        pane scrollback to a file, and kills the session.  The foreground
        process returns immediately so the user's prompt is not blocked.
        """
        if self._client.session_exists(config.session_name):
            raise AppError(
                f"Session '{config.session_name}' already exists."
                " Choose a different name or kill the existing session first."
            )

        self._client.new_session(config.session_name)
        for cmd in config.commands:
            self._client.send_keys(config.session_name, _DEFAULT_WINDOW, _DEFAULT_PANE, cmd)

        n = len(config.commands)
        print(
            f"Session '{config.session_name}' started"
            f" with {n} command{'s' if n != 1 else ''}."
        )

        if config.kill:
            # Queue sentinel after user commands so its appearance in the
            # scrollback proves all preceding commands have completed.
            self._client.send_keys(
                config.session_name, _DEFAULT_WINDOW, _DEFAULT_PANE, f"echo {_SENTINEL}"
            )
            out_path = Path(config.output) if config.output else Path(
                f"/tmp/{config.session_name}.capture-pane"
            )
            log_path = Path(f"/tmp/{config.session_name}.monitor.log")

            daemon_pid = _daemonize(
                _monitor_loop,
                self._client,
                config.session_name,
                _DEFAULT_WINDOW,
                _DEFAULT_PANE,
                out_path,
                log_path,
            )
            print(
                f"Monitor PID {daemon_pid} running in background.\n"
                f"  output → '{out_path}'\n"
                f"  log    → '{log_path}'"
            )

        return 0

    def _wait_for_done(self, session: str, window: str, pane: str) -> str:
        """Poll capture-pane until the sentinel OUTPUT line appears; return the output.

        **Why exact-line matching, not substring search**

        ``send_keys`` writes keystrokes to the PTY master.  The PTY driver
        immediately echoes every character back into the pane (terminal echo),
        so the command text ``echo __tmw_job_done__`` is visible in
        the pane the instant the keys are sent — before the shell has started
        executing *anything*.  That echoed line **contains** the sentinel
        string and would cause a naïve ``_SENTINEL in raw`` check to return
        immediately, killing the session before any user command runs.

        Exact-line matching (``.strip() == _SENTINEL``) distinguishes the
        two cases:

        * ``echo __tmw_job_done__``  — command echo; **not** a match
        * ``__tmw_job_done__``        — actual echo output; **match**

        The sentinel output only appears after the shell has finished every
        preceding command and executed ``echo <sentinel>``, so the match is a
        reliable completion signal.

        Both sentinel-related lines are stripped from the returned text so the
        saved file contains only the actual command output.

        Also checks *session_exists* on each iteration so a session killed
        externally produces a clear error rather than a confusing timeout.

        Raises *AppError* if the session disappears or the timeout expires.
        """
        _sentinel_cmd = f"echo {_SENTINEL}"
        deadline = time.monotonic() + _POLL_TIMEOUT_S
        while time.monotonic() < deadline:
            if not self._client.session_exists(session):
                raise AppError(
                    f"Session '{session}' disappeared while waiting"
                    " for commands to finish."
                )
            raw = self._client.capture_pane(session, window, pane)
            lines = raw.splitlines()
            if any(line.strip() == _SENTINEL for line in lines):
                # Strip the sentinel output line and the echoed command line —
                # both are tmw artefacts, not user output.
                clean = "\n".join(
                    line
                    for line in lines
                    if line.strip() != _SENTINEL
                    and line.strip() != _sentinel_cmd
                )
                return clean
            time.sleep(_POLL_INTERVAL_S)
        raise AppError(
            f"Timed out ({_POLL_TIMEOUT_S:.0f}s) waiting for session"
            f" '{session}' to finish."
        )


# ---------------------------------------------------------------------------
# Background daemon helpers
# ---------------------------------------------------------------------------


def _monitor_loop(
    client: TmuxClient,
    session: str,
    window: str,
    pane: str,
    out_path: Path,
    log_path: Path,
) -> None:
    """Run the wait→capture→write→kill loop; append status to *log_path*.

    This function is intended to run inside a double-fork daemon process.
    All exceptions are caught and written to *log_path* so errors are
    visible even though the process is fully detached.
    """
    runner = SessionRunner(client)
    try:
        output_text = runner._wait_for_done(session, window, pane)
        out_path.write_text(output_text, encoding="utf-8")
        client.kill_session(session)
        log_path.write_text(
            f"[DONE] session='{session}' output='{out_path}'\n",
            encoding="utf-8",
        )
    except AppError as exc:
        log_path.write_text(
            f"[ERROR] session='{session}' {exc}\n",
            encoding="utf-8",
        )
    except Exception as exc:  # noqa: BLE001
        log_path.write_text(
            f"[ERROR] session='{session}' unexpected: {exc}\n",
            encoding="utf-8",
        )


def _daemonize(fn: Callable, *args) -> int:
    """Spawn *fn(*args)* as a double-fork POSIX daemon; return the daemon PID.

    Double-fork pattern:
      1. Fork once.  Parent waits for the intermediate child to exit.
      2. Intermediate child calls ``setsid()`` (new session, no controlling
         terminal) then forks again and exits immediately.
      3. Grandchild (the real daemon) closes inherited file descriptors,
         redirects stdin/stdout/stderr to /dev/null, and calls *fn*.

    The parent receives the daemon PID via a ``os.pipe`` written by the
    grandchild before it does any work, then waits for the intermediate
    child to exit and returns.
    """
    r_fd, w_fd = os.pipe()

    pid = os.fork()
    if pid != 0:
        # ── Parent ────────────────────────────────────────────────────────
        os.close(w_fd)
        os.waitpid(pid, 0)          # reap intermediate child
        raw = os.read(r_fd, 64)     # grandchild PID as ASCII digits
        os.close(r_fd)
        return int(raw.strip())

    # ── Intermediate child ────────────────────────────────────────────────
    os.close(r_fd)
    os.setsid()                     # detach from controlling terminal

    pid2 = os.fork()
    if pid2 != 0:
        # Intermediate child: send grandchild PID to parent then exit.
        os.write(w_fd, str(pid2).encode())
        os.close(w_fd)
        os._exit(0)

    # ── Grandchild (daemon) ───────────────────────────────────────────────
    os.close(w_fd)

    # Redirect stdin / stdout / stderr to /dev/null so the daemon is fully
    # detached from the terminal.
    devnull = os.open(os.devnull, os.O_RDWR)
    for fd in (sys.stdin.fileno(), sys.stdout.fileno(), sys.stderr.fileno()):
        try:
            os.dup2(devnull, fd)
        except Exception:
            pass
    os.close(devnull)

    try:
        fn(*args)
    except Exception:
        pass
    finally:
        os._exit(0)
