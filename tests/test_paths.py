from pathlib import Path, PureWindowsPath

from castero.paths import AppPaths, custom_download_path, download_path


class FakePlatformDirs:
    user_config_path = Path("/native/config/castero")
    user_data_path = Path("/native/data/castero")


def test_app_paths_uses_platform_directories():
    paths = AppPaths(FakePlatformDirs())

    assert paths.config_dir == Path("/native/config/castero")
    assert paths.data_dir == Path("/native/data/castero")
    assert paths.download_dir == Path("/native/data/castero/downloaded")


def test_download_path_uses_default_for_blank_value():
    paths = AppPaths(FakePlatformDirs())

    assert download_path("  ", paths=paths) == paths.download_dir


def test_app_paths_preserves_existing_legacy_directories(tmp_path):
    legacy_config = tmp_path / "legacy-config" / "castero"
    legacy = tmp_path / "legacy" / "castero"
    legacy_config.mkdir(parents=True)
    legacy.mkdir(parents=True)
    directories = FakePlatformDirs()
    directories.user_config_path = tmp_path / "native-config" / "castero"
    directories.user_data_path = tmp_path / "native" / "castero"

    paths = AppPaths(
        directories,
        legacy_config_dir=legacy_config,
        legacy_data_dir=legacy,
    )

    assert paths.config_dir == legacy_config
    assert paths.data_dir == legacy


def test_app_paths_prefers_existing_native_data(tmp_path):
    legacy = tmp_path / "legacy" / "castero"
    native = tmp_path / "native" / "castero"
    legacy.mkdir(parents=True)
    native.mkdir(parents=True)
    directories = FakePlatformDirs()
    directories.user_data_path = native

    paths = AppPaths(directories, legacy_data_dir=legacy)

    assert paths.data_dir == native


def test_custom_download_path_preserves_posix_absolute_path():
    assert custom_download_path("/media/podcasts") == Path("/media/podcasts")


def test_custom_download_path_preserves_windows_drive_path():
    path = custom_download_path(r"D:\\Podcasts", path_type=PureWindowsPath)

    assert path == PureWindowsPath(r"D:\\Podcasts")
    assert path.drive == "D:"
    assert path.is_absolute()


def test_custom_download_path_preserves_windows_unc_path():
    path = custom_download_path(r"\\server\share\Podcasts", path_type=PureWindowsPath)

    assert path == PureWindowsPath(r"\\server\share\Podcasts")
    assert path.drive == r"\\server\share"
    assert path.is_absolute()
