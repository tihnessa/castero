"""Platform-native filesystem locations used by castero."""

import os
from pathlib import Path
import sys

from platformdirs import PlatformDirs

import castero


class AppPaths:
    """Resolve castero's user-writable directories for the current platform."""

    def __init__(self, directories=None, legacy_config_dir=None, legacy_data_dir=None) -> None:
        self._directories = directories or PlatformDirs(castero.__title__, appauthor=False)
        if sys.platform == "darwin":
            if legacy_config_dir is None:
                legacy_config_dir = Path.home() / ".config" / castero.__title__
            if legacy_data_dir is None:
                legacy_data_dir = Path.home() / ".local" / "share" / castero.__title__
        self._legacy_config_dir = (
            Path(legacy_config_dir) if legacy_config_dir is not None else None
        )
        self._legacy_data_dir = Path(legacy_data_dir) if legacy_data_dir is not None else None

    @property
    def config_dir(self) -> Path:
        native = Path(self._directories.user_config_path)
        if (
            self._legacy_config_dir is not None
            and self._legacy_config_dir.exists()
            and not native.exists()
        ):
            return self._legacy_config_dir
        return native

    @property
    def data_dir(self) -> Path:
        native = Path(self._directories.user_data_path)
        if (
            self._legacy_data_dir is not None
            and self._legacy_data_dir.exists()
            and not native.exists()
        ):
            return self._legacy_data_dir
        return native

    @property
    def download_dir(self) -> Path:
        return self.data_dir / "downloaded"


APP_PATHS = AppPaths()


def custom_download_path(value: str, path_type=Path):
    """Expand a configured path without applying POSIX-only transformations."""
    return path_type(os.path.expandvars(os.path.expanduser(value.strip())))


def download_path(value: str = "", paths=APP_PATHS, default=None):
    """Return the configured download directory or the platform default."""
    if value is None or not value.strip():
        return Path(default) if default is not None else paths.download_dir
    return custom_download_path(value)
