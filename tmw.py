#!/usr/bin/env python3.11
"""Backward-compatible entry-point shim.

Kept so existing invocations (`./tmw.py`) continue to work without
change.  All real logic now lives in the tmux_wrapper package; this file
just ensures the package is importable and delegates to its entrypoint.
"""

import sys
from pathlib import Path

# The tmux_wrapper package lives one level up from this shim.
# Insert that parent directory at the front of sys.path so the package
# import below resolves correctly regardless of the caller's cwd.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tmux_wrapper.__main__ import entrypoint  # noqa: E402

raise SystemExit(entrypoint())
