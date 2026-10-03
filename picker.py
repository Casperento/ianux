"""Numbered interactive picker shared by 'attach', 'dump', 'kill' and 'load'."""

from typing import Callable, Sequence, TypeVar

from .exceptions import AppError
from .tmux import TmuxClient

T = TypeVar("T")


def print_numbered(heading: str, items: Sequence[T], label: Callable[[T], str] = str) -> None:
    """Print *heading* followed by ``[i] label(item)`` lines, 1-based."""
    print(heading)
    for i, item in enumerate(items, start=1):
        print(f"  [{i}] {label(item)}")


def pick(
    items: Sequence[T],
    prompt_fn: Callable[[str], str],
    *,
    heading: str,
    prompt: str,
    label: Callable[[T], str] = str,
) -> T:
    """List *items*, prompt for a 1-based index, and return the chosen item.

    Raises AppError on non-numeric or out-of-range input.
    """
    print_numbered(heading, items, label)
    raw = prompt_fn(f"{prompt} (1-{len(items)}): ").strip()
    try:
        idx = int(raw)
    except ValueError:
        raise AppError(f"Invalid selection: '{raw}'")
    if idx < 1 or idx > len(items):
        raise AppError(f"Selection out of range: {raw}")
    return items[idx - 1]


def pick_session(
    client: TmuxClient,
    prompt_fn: Callable[[str], str],
    prompt: str = "Select a session",
) -> str:
    """Pick one open tmux session by number; raises AppError if none are open."""
    sessions = client.list_sessions_names()
    if not sessions:
        raise AppError("No tmux sessions are currently open.")
    return pick(sessions, prompt_fn, heading="Open tmux sessions:", prompt=prompt)
