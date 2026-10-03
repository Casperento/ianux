"""Shared exception type for expected, user-facing errors."""


class AppError(Exception):
    """Raised for all expected operational errors; caught by entrypoint()."""
