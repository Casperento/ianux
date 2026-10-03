"""SessionLister: list existing tmux sessions."""
import re
from dataclasses import dataclass, field

from .config import ListConfig
from .tmux import TmuxClient

# ANSI colour / style codes
_RESET  = "\033[0m"
_BOLD   = "\033[1m"
_DIM    = "\033[2m"
_CYAN   = "\033[36m"
_GREEN  = "\033[32m"
_YELLOW = "\033[33m"

# Cycle through a small palette so adjacent sessions are visually distinct
_PALETTE = [_CYAN, _GREEN, _YELLOW]

# Matches:  name: N windows (created DayOfWeek Mon DD HH:MM:SS YYYY) [WxH]
_SESSION_RE = re.compile(
    r"^(?P<name>.+?)"
    r":\s*(?P<windows>\d+) windows"
    r"\s+\(created (?P<created>[^)]+)\)"
    r"\s+\[(?P<size>\d+x\d+)\]"
)

_HDR_WIN = "Window(s)/Pane(s)"


@dataclass
class _Session:
    """Parsed fields for one tmux session, as shown by ``tmux list-sessions``."""

    name:      str
    windows:   str
    created:   str
    size:      str
    win_panes: dict[str, list[str]] = field(default_factory=dict)


def _parse(line: str) -> _Session | None:
    """Parse one line of ``tmux list-sessions`` output into a ``_Session``."""
    m = _SESSION_RE.match(line.strip())
    if not m:
        return None
    # Simplify the timestamp: "Wed Aug 19 05:58:11 2026" → "Aug 19 2026  05:58"
    raw = m.group("created").strip()
    try:
        parts = raw.split()          # DayOfWeek Mon DD HH:MM:SS YYYY
        created = f"{parts[1]} {parts[2]} {parts[4]}  {parts[3][:5]}"
    except IndexError:
        created = raw
    return _Session(
        name    = m.group("name"),
        windows = m.group("windows"),
        created = created,
        size    = m.group("size"),
    )


def _win_pane_parts(win_panes: dict[str, list[str]]) -> list[tuple[str, str]]:
    """Return ``(left_part, count_part)`` per window (unsized; caller aligns).

    Example::

        [('0 : 0, 1, 2', '(3 panes)'), ('1 : 0', '(1 pane)')]
    """
    parts = []
    for win in sorted(win_panes.keys(), key=lambda x: (int(x) if x.isdigit() else x)):
        panes = win_panes[win]
        left  = f"{win} : {', '.join(panes)}"
        count = len(panes)
        noun  = "pane" if count == 1 else "panes"
        parts.append((left, f"({count} {noun})"))
    return parts


class SessionLister:
    """Handles the 'list' subcommand: pretty-print open tmux sessions."""

    def __init__(self, client: TmuxClient) -> None:
        self._client = client

    def list(self, config: ListConfig) -> int:
        """Pretty-print existing tmux sessions.

        Output::

            Sessions
            ────────────────────────────────────────────────────────────────
              #   Name                         Window(s)/Pane(s)          Created              Size
              1   my-session                   0 : 0  (1 pane)            Aug 19 2026  05:58   270x72
              2   tmw-session-name             0 : 0, 1, 2  (3 panes)    Aug 20 2026  10:10   236x64
                                               1 : 0  (1 pane)

        Returns 0 on success.
        """
        raw_lines = self._client.list_sessions()

        sessions = [s for s in (_parse(l) for l in raw_lines) if s is not None]
        # Sort by name (not the raw line) so IDs line up with list_sessions_names(),
        # which 'attach'/'kill' use — keeps the # column a stable cross-command ID.
        sessions.sort(key=lambda s: s.name)

        # Augment each session with per-window/pane detail (one tmux call each)
        for s in sessions:
            s.win_panes = self._client.list_panes_all(s.name)

        header = f"{_BOLD}Sessions{_RESET}"

        if not sessions:
            rule = f"{_DIM}{'─' * 32}{_RESET}"
            print(f"\n{header}\n{rule}")
            print(f"  {_DIM}(no sessions){_RESET}\n")
            return 0

        # Pass 1 — collect raw (left, count) parts for every window across all sessions
        wp_parts: list[list[tuple[str, str]]] = []
        for s in sessions:
            if s.win_panes:
                wp_parts.append(_win_pane_parts(s.win_panes))
            else:
                # Fallback: just show window count from list-sessions
                wp_parts.append([(s.windows, "")])

        all_pairs = [pair for parts in wp_parts for pair in parts]
        max_left_w  = max(len(left)  for left,  _     in all_pairs)
        max_count_w = max((len(count) for _,    count in all_pairs if count), default=0)

        # Pass 2 — format with globally consistent alignment:
        #   "win : panes" left-padded to max_left_w,  "(N panes)" right-padded to max_count_w
        def _fmt(left: str, count: str) -> str:
            if count:
                return f"{left:<{max_left_w}}  {count:>{max_count_w}}"
            return left

        wp_lines: list[list[str]] = [
            [_fmt(left, count) for left, count in parts]
            for parts in wp_parts
        ]

        # Column widths
        idx_w  = len(str(len(sessions)))
        name_w = max(len(s.name) for s in sessions)
        win_w  = max(
            len(_HDR_WIN),
            max_left_w + (2 + max_count_w if max_count_w else 0),
        )
        dat_w  = max(max(len(s.created) for s in sessions), 7)   # at least "Created"
        size_w = max(max(len(s.size)    for s in sessions), 4)   # at least "Size"

        # Rule width matches the rendered row: "  idx  name  win  created  size"
        row_w  = 2 + idx_w + 2 + max(name_w, 4) + 2 + win_w + 2 + dat_w + 2 + size_w
        rule   = f"{_DIM}{'─' * row_w}{_RESET}"
        print(f"\n{header}\n{rule}")

        # Header row (Created and Size right-aligned)
        h_idx  = "#".ljust(idx_w)
        h_name = "Name".ljust(name_w)
        h_win  = _HDR_WIN.ljust(win_w)
        h_dat  = "Created".rjust(dat_w)
        h_size = "Size".rjust(size_w)
        print(
            f"  {_DIM}{h_idx}  {h_name}  {h_win}  {h_dat}  {h_size}{_RESET}"
        )

        # Leading spaces to align continuation lines under the Window(s)/Pane(s) column
        cont_prefix = " " * (2 + idx_w + 2 + name_w + 2)

        for i, (s, wpl) in enumerate(zip(sessions, wp_lines), start=1):
            colour = _PALETTE[(i - 1) % len(_PALETTE)]
            idx    = str(i).ljust(idx_w)
            name   = s.name.ljust(name_w)
            dat    = s.created.rjust(dat_w)
            size   = s.size.rjust(size_w)

            # First window on the same row as the session name
            first_win = wpl[0].ljust(win_w)
            print(
                f"  {_DIM}{idx}{_RESET}"
                f"  {colour}{_BOLD}{name}{_RESET}"
                f"  {_DIM}{first_win}  {dat}  {size}{_RESET}"
            )

            # Additional windows as indented continuation lines
            for extra in wpl[1:]:
                print(f"{cont_prefix}{_DIM}{extra}{_RESET}")

        print()
        return 0
