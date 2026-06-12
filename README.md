# QA Helper

`qahelper` is a command-line tool for organizing QA scenarios and saving
screenshots as numbered evidence.

It creates one directory per scenario, keeps track of the active scenario and
provides a Rich-powered dashboard for reviewing the collected evidence.

## Requirements

- Linux
- Python 3.10 or newer
- [`uv`](https://docs.astral.sh/uv/)

Screenshot support depends on the desktop environment:

- GNOME on Wayland uses the native screenshot portal.
- Other Wayland compositors can use `grim`.
- X11 can use `gnome-screenshot`, `scrot` or ImageMagick's `import`.

## Installation

Install the published package from PyPI:

```bash
uv tool install qahelper
```

Install the current checkout during development:

```bash
uv tool install .
```

Upgrade an existing installation:

```bash
uv tool upgrade qahelper
```

Confirm that the command is available:

```bash
qahelper --help
```

## Usage

Choose the directory where the QA data should be stored and start a scenario:

```bash
mkdir -p "$HOME/QA"
cd "$HOME/QA"
qahelper qa scenario start "Lead without account"
```

This creates:

```text
qa-scenarios/TC-001-lead-without-account/
```

Starting a scenario with the same normalized name resumes the existing
directory and marks it as active.

### Review scenarios

List all scenarios:

```bash
qahelper qa scenario list
```

Show the active scenario:

```bash
qahelper qa scenario current
```

Show totals, the active scenario and evidence counts:

```bash
qahelper qa scenario dashboard
```

### Capture evidence

Capture the entire screen using the next available number:

```bash
qahelper qa scenario add-screenshot
```

Set the evidence order explicitly:

```bash
qahelper qa scenario add-screenshot --order 3
```

Open the native screenshot selector to capture a specific window:

```bash
qahelper qa scenario add-screenshot --window
```

Wait before starting the capture:

```bash
qahelper qa scenario add-screenshot --window --delay 5
```

Screenshots are stored as `001.png`, `002.png` and so on inside the active
scenario directory. Existing numbers are never overwritten.

## Keyboard shortcut on GNOME

Open:

```text
Settings > Keyboard > View and Customize Shortcuts > Custom Shortcuts
```

Create a shortcut named `QA Screenshot` with:

```bash
bash -lc 'cd "$HOME/QA" && qahelper qa scenario add-screenshot --window --delay 2'
```

Replace `$HOME/QA` with the directory where scenarios should be stored. Start
at least one scenario from that directory before using the shortcut.

## Data layout

```text
QA/
├── .qahelper/
│   └── state.json
└── qa-scenarios/
    ├── TC-001-lead-without-account/
    │   ├── 001.png
    │   └── 002.png
    └── TC-002-lead-converted/
        └── 001.png
```

`.qahelper/state.json` stores only the active scenario. All evidence remains in
regular directories and PNG files.

## Development

Install the project environment and run the test suite:

```bash
uv sync
uv run python -m unittest -v
```

Build the distributions:

```bash
uv build
```

The generated wheel and source distribution are written to `dist/`.

## License

MIT
