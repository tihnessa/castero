# castero

[![GitHub release](https://img.shields.io/github/release/xgi/castero.svg?style=flat-square)](https://github.com/xgi/castero/releases) [![PyPI](https://img.shields.io/pypi/v/castero.svg?style=flat-square)](https://pypi.org/project/castero) [![GitHub Build](https://img.shields.io/github/actions/workflow/status/xgi/castero/ci.yml?branch=master&style=flat-square)](https://circleci.com/gh/xgi/castero/tree/master) [![Maintainability](https://api.codeclimate.com/v1/badges/babcaad5cb2cca266c92/maintainability)](https://codeclimate.com/github/xgi/castero/maintainability) [![Test Coverage](https://api.codeclimate.com/v1/badges/babcaad5cb2cca266c92/test_coverage)](https://codeclimate.com/github/xgi/castero/test_coverage)

castero is a TUI podcast client for the terminal.

![example client screenshot](https://raw.githubusercontent.com/xgi/castero/master/res/client_example.png)

## Installation

Install from [PyPi](https://pypi.org/project/castero) with pip:

```bash
$ pip3 install castero
```

Upgrading:

```bash
$ pip3 install castero --upgrade
```

### Manual Installation

```bash
$ git clone https://github.com/xgi/castero
$ cd castero
$ sudo python setup.py install
```

## Dependencies

Running castero requires Python 3.9 or newer and one or both native media
players. Installing both allows the `player` setting to select either backend.

| Platform | Native dependencies |
| --- | --- |
| Ubuntu/Debian | `sudo apt install vlc mpv libmpv2` |
| macOS with Homebrew | `brew install --cask vlc && brew install mpv` |
| Windows | `choco install vlc`; download the matching-architecture `mpv-dev` archive from the [official Windows builds](https://sourceforge.net/projects/mpv-player-windows/files/libmpv/) and add its extracted directory to `PATH` |

The native player and Python must use the same architecture. On Windows,
`libvlc.dll` or `mpv-2.dll`/`libmpv-2.dll` must be discoverable through the
normal installation location or `PATH`. castero reports backend-specific setup
guidance when a Python binding is installed but its native library cannot be
loaded.

The Windows installation automatically includes `windows-curses`. Use a modern
interactive console such as Windows Terminal, PowerShell, or Command Prompt.
Linux and macOS require a terminal with curses and color support.
## Usage

After installing castero, it can be run with simply:

```bash
$ castero
```

The help menu provides a list of controls and can be accessed by pressing
<kbd>h</kbd>. Alternatively, see the list below:

```text
Commands
    h           - show this help screen
    q           - exit the client
    a           - add a feed
    d           - delete the selected feed
    r           - reload/refresh feeds
    s           - save episode for offline playback
    UP/DOWN     - navigate up/down in menus
    RIGHT/LEFT  - navigate right/left in menus
    PPAGE/NPAGE - scroll up/down in menus
    ENTER       - play selected feed/episode
    SPACE       - add selected feed/episode to queue
    c           - clear the queue
    n           - go to the next episode in the queue
    i           - invert the order of the menu
    /           - filter the contents of the menu
    m           - mark episode as played/unplayed
    p or k      - pause/play the current episode
    f or l      - seek forward
    b or j      - seek backward
    =/-         - increase/decrease volume
    ]/[         - increase/decrease playback speed
    u           - show episode URL
    1-5         - change between client layouts
```

Episode menus sort publication dates by their normalized UTC time. Episodes
with missing or malformed publication dates appear last in the default
newest-first order and first when the menu order is inverted.

### Importing/exporting feeds from another client

castero supports importing and exporting an [OPML file](https://en.wikipedia.org/wiki/OPML)
of your subscriptions in order to easily transfer them between other podcast
clients. Imports discover feeds in nested folder or group outlines. Please refer
to your other client's documentation for details on how/if it supports this
format.

Importing and exporting from castero are available with command line flags.
Run `castero --help` for details.

### Verifying the database and downloads

Run the following command to check castero's persisted SQLite database and
downloaded episodes without starting the terminal interface:

```bash
$ castero --verify
```

Verification runs SQLite integrity and foreign-key checks, validates castero's
records, inventories the active download directory, and compares tracked files
with the SHA-256 checksums saved when their downloads completed. It reports
missing, unreadable, duplicate, unexpected, and modified files. The configured
`custom_download_dir` is honored.

When run in an interactive terminal, castero offers repairs appropriate to each
problem, such as removing an invalid record or file, redownloading an episode,
or explicitly trusting an existing file as the checksum baseline. Existing
downloads from older castero versions are reported as unverified until they are
redownloaded or explicitly trusted. When input or output is redirected, the
command is report-only and never changes data.

Before the first database repair, castero creates a timestamped backup beside
`castero.db`, named `castero.db.verify-backup-<timestamp>`. Low-level SQLite
corruption is reported but is not rewritten automatically. The command exits
with status `0` only when no problems remain and status `1` otherwise.

## Configuration

Configuration and user data follow each operating system's native conventions:

| Platform | Configuration | User data and downloads |
| --- | --- | --- |
| Linux | `$XDG_CONFIG_HOME/castero/castero.conf` or `~/.config/castero/castero.conf` | `$XDG_DATA_HOME/castero` or `~/.local/share/castero` |
| macOS | `~/Library/Application Support/castero/castero.conf` | `~/Library/Application Support/castero` |
| Windows | `%LOCALAPPDATA%\\castero\\castero.conf` | `%LOCALAPPDATA%\\castero` |

Linux locations remain compatible with previous castero releases. On macOS,
existing legacy `~/.config/castero` and `~/.local/share/castero` directories
continue to be used until they are moved to the native location. The files are
created after the client is run for the first time.

Please see the [default castero.conf](https://github.com/xgi/castero/blob/master/castero/templates/castero.conf)
for a list of available settings.

User data includes downloaded episodes and a database containing feed
information and the saved playback queue. The `custom_download_dir` setting
accepts POSIX paths, Windows drive-letter paths such as `D:\\Podcasts`, UNC
paths such as `\\\\server\\share\\Podcasts`, environment variables, and `~`.
By default, castero works from an in-memory copy and writes it to `castero.db`
on clean shutdown. The preceding on-disk database is retained as
`castero.db.old`, replacing an earlier backup when necessary.
Refreshing feeds preserves queued episodes that remain in those feeds. Deleting
a feed also deletes its downloaded episodes. These files are not intended to be
manually modified.

### Platform troubleshooting

- If startup says curses is unavailable on Windows, reinstall castero so its
  conditional `windows-curses` dependency is installed, then use an interactive
  Windows console rather than an IDE output pane.
- If a backend cannot load, confirm the native player and Python have matching
  32/64-bit or ARM architectures and restart the terminal after changing
  `PATH`.
- VLC's Python binding also honors `PYTHON_VLC_LIB_PATH` and
  `PYTHON_VLC_MODULE_PATH` for non-standard installations.
- mpv on Windows requires a build that includes the libmpv DLL; an `mpv.exe`
  by itself is insufficient.

## Testing

This project uses [pytest](https://pytest.org) for testing. To run tests, run
the following command in the project's root directory:

```bash
$ python -m pytest tests
```

You can also run tests for an individual unit, i.e.:

```bash
$ python -m pytest tests/test_feed.py
```

## License

[MIT License](https://github.com/xgi/castero/blob/master/LICENSE.txt)
