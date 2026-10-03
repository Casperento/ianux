# Installation and setup

## Requirements

- Python 3.11 or later
- [uv](https://docs.astral.sh/uv/) for installation and project commands
- `tmux` installed separately and available on `PATH`

## Install as a command

From the project checkout:

```bash
uv tool install .
ianux --help
```

Then run commands directly, for example:

```bash
ianux session --panes 4
ianux list
```

## Run from a checkout

Sync the development environment, then run Ianux through uv:

```bash
uv sync
uv run ianux --help
uv run ianux session --panes 4
```

## Build distributions

Build a wheel and source distribution in `dist/`:

```bash
uv build
```

Use `uv build --clear` to clear previous build outputs first. To install the resulting wheel as a standalone tool:

```bash
uv tool install dist/ianux-*.whl
```

See [Development and testing](Development.md) for running tests and contributing from a checkout.
