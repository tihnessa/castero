import curses
import os
import tempfile
import threading
from unittest import mock

import pytest

from gevent import monkey

# Keep test-created configuration, databases, and downloads out of a
# developer's real XDG directories.  These must be set before castero imports
# DataFile, which resolves the paths at import time.
TEST_XDG_ROOT = tempfile.mkdtemp(prefix="castero-pytest-")
os.environ["XDG_CONFIG_HOME"] = os.path.join(TEST_XDG_ROOT, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(TEST_XDG_ROOT, "data")

monkey.patch_all(thread=False, select=False)

import castero.config
from castero.datafile import DataFile
from castero.display import Display
from castero.database import Database


@pytest.fixture(autouse=True)
def run_background_work_synchronously(monkeypatch):
    """Prevent UI worker threads from outliving their test's database/window."""

    original_start = threading.Thread.start

    def run(thread):
        target_module = getattr(thread._target, "__module__", "")
        if not target_module.startswith(("castero.menus", "castero.database")):
            return original_start(thread)

        try:
            thread.run()
        except curses.error:
            # Some unit tests intentionally construct menus without curses.
            # Their production worker would otherwise report this asynchronously.
            pass

    monkeypatch.setattr(threading.Thread, "start", run)


class Helpers:
    """Provides functions that are useful to multiple test units."""

    @staticmethod
    def hide_user_database():
        """Moves the user's database files to make them unreachable."""
        DataFile.ensure_path(Database.PATH)
        DataFile.ensure_path(Database.OLD_PATH)
        if os.path.exists(Database.PATH):
            os.rename(Database.PATH, Database.PATH + ".tmp")
        if os.path.exists(Database.OLD_PATH):
            os.rename(Database.OLD_PATH, Database.OLD_PATH + ".tmp")

    @staticmethod
    def restore_user_database():
        """Restores the user's database files if they have been hidden."""
        DataFile.ensure_path(Database.PATH)
        DataFile.ensure_path(Database.OLD_PATH)
        if os.path.exists(Database.PATH + ".tmp"):
            os.rename(Database.PATH + ".tmp", Database.PATH)
        if os.path.exists(Database.OLD_PATH + ".tmp"):
            os.rename(Database.OLD_PATH + ".tmp", Database.OLD_PATH)


class MockStdscr(mock.MagicMock):
    """Provides functions to mock typical stdscr behavior."""

    def getstr(self, start, end):
        return self.test_input.encode("utf-8")

    def setmaxyx(self, nlines, ncols):
        self.nlines, self.ncols = nlines, ncols

    def getmaxyx(self):
        return self.nlines, self.ncols

    def derwin(self, nlines, ncols, x, y):
        return MockStdscr(nlines=nlines, ncols=ncols, x=x, y=y, test_input="unspecified test input")

    def set_test_input(self, str):
        self.test_input = str


@pytest.yield_fixture()
def stdscr():
    with mock.patch("curses.initscr"), mock.patch("curses.echo"), mock.patch("curses.flash"), mock.patch(
        "curses.endwin"
    ), mock.patch("curses.newwin"), mock.patch("curses.newpad"), mock.patch("curses.noecho"), mock.patch(
        "curses.cbreak"
    ), mock.patch(
        "curses.doupdate"
    ), mock.patch(
        "curses.nocbreak"
    ), mock.patch(
        "curses.curs_set"
    ), mock.patch(
        "curses.init_pair"
    ), mock.patch(
        "curses.color_pair"
    ), mock.patch(
        "curses.has_colors"
    ), mock.patch(
        "curses.start_color"
    ), mock.patch(
        "curses.use_default_colors"
    ):
        result = MockStdscr(nlines=24, ncols=100, x=0, y=0)
        curses.initscr.return_value = result
        curses.newwin.side_effect = lambda *args: result.derwin(*args)
        curses.color_pair.return_value = 1
        curses.has_colors.return_value = True
        curses.ACS_VLINE = 0
        curses.ACS_HLINE = 0
        curses.COLORS = 16
        curses.COLOR_PAIRS = 16
        yield result


@pytest.yield_fixture()
def prevent_modification():
    Helpers.hide_user_database()
    yield
    Helpers.restore_user_database()


@pytest.yield_fixture()
def display(prevent_modification, stdscr):
    database = Database()
    yield Display(stdscr, database)


@pytest.fixture(autouse=True)
def restore_config_data():
    yield
    castero.config.Config.data = castero.config._Config().data
