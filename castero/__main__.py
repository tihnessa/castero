import argparse
from contextlib import contextmanager
import os
import re
import sys
import tempfile
import threading

from gevent import monkey

monkey.patch_all(thread=False, select=False)

import castero
from castero import helpers
from castero.config import Config
from castero.database import Database
from castero.feed import Feed
from castero.subscriptions import Subscriptions
from castero.verify import run_verify


class TerminalDependencyError(RuntimeError):
    """The platform does not provide a usable curses implementation."""


def import_subscriptions(path: str, database: Database) -> None:
    subscriptions = Subscriptions()
    subscriptions.load(path)

    for generated in subscriptions.parse():
        if isinstance(generated, Feed):
            feed = generated
            database.replace_feed(feed)
            episodes = feed.parse_episodes()
            database.replace_episodes(feed, episodes)
            print('Added "%s" with %d episodes' % (str(feed), len(episodes)))
        else:
            print("ERROR: Failed to load %s -- %s" % (str(generated[0]), str(generated[1])))

    database.close()
    print("Imported %d feeds" % len(subscriptions.feeds))


def export_subscriptions(path: str, database: Database) -> None:
    subscriptions = Subscriptions()
    feeds = database.feeds()
    subscriptions.generate(feeds)
    subscriptions.save(path)
    print("Exported %d feeds" % len(feeds))


@contextmanager
def suppress_stderr():
    """Temporarily redirect Python and native-library stderr output."""
    with tempfile.TemporaryFile(prefix="%s-" % castero.__title__) as temp_file:
        try:
            stderr_fd = sys.stderr.fileno()
        except (AttributeError, OSError, ValueError):
            yield temp_file
            return

        saved_fd = os.dup(stderr_fd)
        sys.stderr.flush()
        os.dup2(temp_file.fileno(), stderr_fd)
        try:
            yield temp_file
        finally:
            sys.stderr.flush()
            os.dup2(saved_fd, stderr_fd)
            os.close(saved_fd)


def _display_loop(stdscr, database) -> None:
    from castero.display import Display

    display = Display(stdscr, database)
    try:
        display.clear()
        display.update_parent_dimensions()

        if helpers.is_true(Config["reload_on_start"]):
            reload_thread = threading.Thread(target=database.reload, args=[display])
            reload_thread.start()

        display.display_all()
        display._menus_valid = False
        display._update_timer = 0

        running = True
        while running:
            display.display()
            char = display.getch()
            if char != -1:
                running = display.handle_input(char)
    finally:
        display.terminate()


def run_tui(database) -> None:
    try:
        import curses
    except ImportError as error:
        raise TerminalDependencyError(
            "Python curses support is unavailable. On native Windows, install "
            "the windows-curses package and run castero in a supported console."
        ) from error

    with suppress_stderr():
        try:
            curses.wrapper(_display_loop, database)
        except curses.error as error:
            raise TerminalDependencyError(
                "Unable to initialize the terminal. Run castero in a supported interactive console."
            ) from error


def _format_help_keys() -> None:
    for field in Config:
        if "{%s}" % field in castero.__help__:
            castero.__help__ = castero.__help__.replace("{%s}" % field, Config[field].ljust(11))
        elif "{%s|" % field in castero.__help__:
            field2 = castero.__help__.split("{%s|" % field)[1].split("}")[0]
            replacement = ("%s or %s" % (Config[field], Config[field2])).ljust(11)
            castero.__help__ = castero.__help__.replace("{%s|%s}" % (field, field2), replacement)
        elif "{%s/" % field in castero.__help__:
            field2 = castero.__help__.split("{%s/" % field)[1].split("}")[0]
            castero.__help__ = castero.__help__.replace(
                "{%s/%s}" % (field, field2), ("%s/%s" % (Config[field], Config[field2])).ljust(11)
            )

    remaining_brace_fields = re.compile("\\{.*?\\}").findall(castero.__help__)
    for field in remaining_brace_fields:
        adjusted = field.replace("{", "").replace("}", "").ljust(11)
        castero.__help__ = castero.__help__.replace(field, adjusted)


def main(argv=None):
    parser = argparse.ArgumentParser(prog=castero.__title__, description=castero.__description__)
    parser.add_argument(
        "-V", "--version", action="version", version="%(prog)s {}".format(castero.__version__)
    )
    parser.add_argument("--import", help="path to OPML file of feeds to add")
    parser.add_argument("--export", help="path to save feeds as OPML file")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="verify the integrity of the database and downloaded episodes",
    )
    args = parser.parse_args(argv)

    if args.verify:
        return run_verify()

    database = Database()
    if vars(args)["import"] is not None:
        import_subscriptions(vars(args)["import"], database)
        return 0
    if vars(args)["export"] is not None:
        export_subscriptions(vars(args)["export"], database)
        return 0

    _format_help_keys()
    run_tui(database)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
