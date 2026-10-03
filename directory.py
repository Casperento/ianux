"""Direct directory resolution for session working directories."""

from pathlib import Path
from typing import Protocol, runtime_checkable

from .exceptions import AppError


@runtime_checkable
class DirectoryResolver(Protocol):
    """Strategy interface: produce a target directory."""

    def resolve(self) -> Path:
        """Return the target directory."""
        ...


# ---------------------------------------------------------------------------
# Strategy 1 — explicit path supplied via --directory
# ---------------------------------------------------------------------------


class ExplicitResolver:
    """Use the path given by --directory directly."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def resolve(self) -> Path:
        target = self._directory.expanduser().resolve()
        if not target.exists() or not target.is_dir():
            raise AppError(
                f"Target directory does not exist or is not a directory: {target}"
            )
        return target
