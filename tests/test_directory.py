"""Tests for ianux.directory resolvers."""

from pathlib import Path

import pytest

from ianux.directory import ExplicitResolver
from ianux.exceptions import AppError


# ---------------------------------------------------------------------------
# ExplicitResolver
# ---------------------------------------------------------------------------


class TestExplicitResolver:
    def test_valid_directory(self, tmp_path):
        resolver = ExplicitResolver(tmp_path)
        path = resolver.resolve()
        assert path == tmp_path.resolve()

    def test_tilde_expansion(self, tmp_path, monkeypatch):
        """~ in the path should expand correctly."""
        monkeypatch.setenv("HOME", str(tmp_path))
        sub = tmp_path / "mydir"
        sub.mkdir()
        resolver = ExplicitResolver(Path("~/mydir"))
        path = resolver.resolve()
        assert path.exists()

    def test_missing_path_raises(self, tmp_path):
        resolver = ExplicitResolver(tmp_path / "nonexistent")
        with pytest.raises(AppError, match="does not exist"):
            resolver.resolve()
    def test_file_instead_of_dir_raises(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("content")
        resolver = ExplicitResolver(f)
        with pytest.raises(AppError, match="does not exist or is not a directory"):
            resolver.resolve()

