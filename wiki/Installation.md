# Installation and setup

## Requirements

- Python 3.11 or later
- `tmux` installed separately and available on `PATH`

## Install with pip

From the project checkout:

```bash
python -m pip install .
ianux --help
```

Then run commands directly, for example:

```bash
ianux session -p 4
ianux list
```

For an editable installation while developing:

```bash
python -m pip install -e .
```

## Install with uv

If you use [uv](https://docs.astral.sh/uv/), install Ianux as a standalone
command:

```bash
uv tool install .
ianux --help
```

## Run from a checkout

Sync the development environment, then run Ianux through uv:

```bash
uv sync
uv run ianux --help
uv run ianux session -p 4
```

For session window configuration, `-p` is shorthand for `--window-panes` and
`-w` is shorthand for `--window-name`. Both can be repeated once per window.

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
