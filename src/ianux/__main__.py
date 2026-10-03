#!/usr/bin/env python3.11
"""Entry point for `python -m ianux`.

main() accepts an optional argv list so callers (tests, scripts) can drive
the tool without touching sys.argv.  entrypoint() wraps main() with error
handling and is what the shell shim and __name__ == "__main__" both call.
"""

import sys

from .attacher import SessionAttacher
from .cli import build_resolver, parse_args
from .config import AttachConfig, DumpConfig, KillConfig, LoadConfig, RunConfig, ListConfig
from .dumper import SessionDumper
from .exceptions import AppError
from .killer import SessionKiller
from .loader import load_session_config
from .runner import SessionRunner
from .session import SessionManager
from .tmux import TmuxClient
from .lister import SessionLister


def main(argv: list[str] | None = None) -> int:
    """Parse *argv*, dispatch to the matching manager, and return its exit code."""
    config = parse_args(argv)
    client = TmuxClient()

    if isinstance(config, AttachConfig):
        return SessionAttacher(client).attach(config)

    if isinstance(config, KillConfig):
        return SessionKiller(client).kill(config)

    if isinstance(config, RunConfig):
        return SessionRunner(client).run(config)

    if isinstance(config,ListConfig):
        return SessionLister(client).list(config)

    if isinstance(config, DumpConfig):
        return SessionDumper(client).dump(config)

    if isinstance(config, LoadConfig):
        config = load_session_config(config)
        # Falls through to the SessionConfig flow below.

    # SessionConfig — existing multi-pane dev session flow.
    resolver = build_resolver(config)
    return SessionManager(client).setup(config, resolver)


def entrypoint() -> int:
    """Run main(), converting an AppError into a printed message and exit code 1."""
    try:
        return main()
    except AppError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(entrypoint())
