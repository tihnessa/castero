import sys
from unittest import mock

import pytest

import castero.__main__ as cli


def test_import_does_not_run_main():
    assert callable(cli.main)


def test_suppress_stderr_redirects_and_restores_descriptor():
    stderr = mock.MagicMock()
    stderr.fileno.return_value = 2
    temporary_file = mock.MagicMock()
    temporary_file.fileno.return_value = 9
    temporary_file.__enter__.return_value = temporary_file

    with mock.patch.object(sys, "stderr", stderr), mock.patch(
        "castero.__main__.tempfile.TemporaryFile", return_value=temporary_file
    ), mock.patch("castero.__main__.os.dup", return_value=10) as duplicate, mock.patch(
        "castero.__main__.os.dup2"
    ) as duplicate_to, mock.patch("castero.__main__.os.close") as close:
        with cli.suppress_stderr():
            duplicate_to.assert_called_once_with(9, 2)

    duplicate.assert_called_once_with(2)
    assert duplicate_to.call_args_list == [mock.call(9, 2), mock.call(10, 2)]
    close.assert_called_once_with(10)
    assert stderr.flush.call_count == 2


def test_run_tui_uses_curses_wrapper():
    curses = mock.MagicMock()
    database = mock.MagicMock()

    with mock.patch.dict(sys.modules, {"curses": curses}), mock.patch(
        "castero.__main__.suppress_stderr"
    ), mock.patch("castero.__main__._display_loop") as display_loop:
        cli.run_tui(database)

    curses.wrapper.assert_called_once_with(display_loop, database)


def test_run_tui_reports_missing_curses():
    with mock.patch("builtins.__import__", side_effect=ImportError("no curses")):
        with pytest.raises(cli.TerminalDependencyError, match="windows-curses"):
            cli.run_tui(mock.MagicMock())


def test_display_loop_terminates_after_an_error():
    display = mock.MagicMock()
    display.display.side_effect = RuntimeError("render failed")

    with mock.patch("castero.display.Display", return_value=display):
        with pytest.raises(RuntimeError, match="render failed"):
            cli._display_loop(mock.MagicMock(), mock.MagicMock())

    display.terminate.assert_called_once_with()


def test_verify_does_not_construct_normal_database():
    with mock.patch("castero.__main__.Database") as database, mock.patch(
        "castero.__main__.run_verify", return_value=1
    ) as verify:
        status = cli.main(["--verify"])

    assert status == 1
    verify.assert_called_once_with()
    database.assert_not_called()
