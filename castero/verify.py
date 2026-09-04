"""Read-only-first verification and repair for castero user data."""

from dataclasses import dataclass, field
import hashlib
import os
from pathlib import Path, PurePosixPath
import sqlite3
import sys
import time

from castero import helpers
from castero.config import Config
from castero.database import Database
from castero.datafile import DataFile
from castero.paths import download_path


@dataclass
class Finding:
    """A database or download problem discovered during verification."""

    code: str
    message: str
    actions: tuple = ()
    data: dict = field(default_factory=dict)
    fatal: bool = False


class _RepairDownloadQueue:
    """Minimal queue adapter used for synchronous repair downloads."""

    cancelled = False
    length = 1

    def next(self):
        pass


class Verifier:
    """Inspect and optionally repair the persisted database and downloads."""

    CURRENT_SCHEMA_VERSION = 6
    HASH_CHUNK_SIZE = 64 * 1024
    REQUIRED_COLUMNS = {
        "feed": {"key", "title", "description", "link", "last_build_date", "copyright"},
        "episode": {
            "id",
            "feed_key",
            "title",
            "description",
            "link",
            "pubdate",
            "copyright",
            "enclosure",
            "played",
            "guid",
        },
        "queue": {"id", "ep_id"},
        "progress": {"ep_id", "time"},
        "download": {"ep_id", "path", "sha256"},
    }
    COLUMN_DEFINITIONS = {
        "feed": {
            "key": ("TEXT", False, 1, None),
            "title": ("TEXT", False, 0, None),
            "description": ("TEXT", False, 0, None),
            "link": ("TEXT", False, 0, None),
            "last_build_date": ("TEXT", False, 0, None),
            "copyright": ("TEXT", False, 0, None),
        },
        "episode": {
            "id": ("INTEGER", False, 1, None),
            "feed_key": ("TEXT", False, 0, None),
            "title": ("TEXT", False, 0, None),
            "description": ("TEXT", False, 0, None),
            "link": ("TEXT", False, 0, None),
            "pubdate": ("TEXT", False, 0, None),
            "copyright": ("TEXT", False, 0, None),
            "enclosure": ("TEXT", False, 0, None),
            "played": ("BIT", True, 0, "0"),
            "guid": ("TEXT", False, 0, None),
        },
        "queue": {
            "id": ("INTEGER", False, 1, None),
            "ep_id": ("INTEGER", False, 0, None),
        },
        "progress": {
            "ep_id": ("INTEGER", False, 1, None),
            "time": ("INTEGER", False, 0, None),
        },
        "download": {
            "ep_id": ("INTEGER", False, 1, None),
            "path": ("TEXT", True, 0, None),
            "sha256": ("TEXT", True, 0, None),
        },
    }
    REQUIRED_UNIQUE_COLUMNS = {"download": {("path",)}}
    REQUIRED_FOREIGN_KEYS = {
        "episode": {("feed_key", "feed", "key", "NO ACTION", "CASCADE")},
        "queue": {("ep_id", "episode", "id", "NO ACTION", "CASCADE")},
        "progress": {("ep_id", "episode", "id", "NO ACTION", "CASCADE")},
        "download": {("ep_id", "episode", "id", "NO ACTION", "CASCADE")},
    }
    ACTION_LABELS = {
        "migrate": "migrate the database schema",
        "delete_row": "remove the invalid database record",
        "reset_played": "reset the invalid played value",
        "reorder_queue": "rebuild queue positions",
        "forget": "remove stale download metadata",
        "baseline": "trust the current file and store its checksum",
        "redownload": "redownload the episode",
        "remove": "remove the file and its metadata",
        "remove_file": "remove the unexpected file",
    }

    def __init__(self, database_path, download_dir):
        self.database_path = Path(database_path)
        self.download_dir = Path(download_dir)
        self._backup_path = None

    @property
    def backup_path(self):
        """Path: backup created before the first database repair, if any."""
        return self._backup_path

    @staticmethod
    def _database_uri(path, mode):
        return Path(path).resolve().as_uri() + "?mode=" + mode

    @classmethod
    def sha256_file(cls, path):
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            while True:
                chunk = handle.read(cls.HASH_CHUNK_SIZE)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def _finding(self, code, message, actions=(), data=None, fatal=False):
        return Finding(code, message, tuple(actions), data or {}, fatal)

    def scan(self):
        """Return all problems without changing the database or filesystem."""
        if not self.database_path.is_file():
            return [
                self._finding(
                    "database_missing",
                    "Database file does not exist: %s" % self.database_path,
                    fatal=True,
                )
            ]

        connection = None
        try:
            connection = sqlite3.connect(
                self._database_uri(self.database_path, "ro"), uri=True
            )
            connection.execute("PRAGMA query_only = ON")
            integrity_rows = connection.execute("PRAGMA integrity_check").fetchall()
        except sqlite3.DatabaseError as error:
            if connection is not None:
                connection.close()
            return [
                self._finding(
                    "database_unreadable",
                    "Database could not be read: %s" % error,
                    fatal=True,
                )
            ]

        integrity_errors = [row[0] for row in integrity_rows if row[0] != "ok"]
        if integrity_errors:
            connection.close()
            return [
                self._finding(
                    "database_integrity",
                    "SQLite integrity check failed: %s" % "; ".join(integrity_errors),
                    fatal=True,
                )
            ]

        findings = []
        try:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            tables = {
                row[0]
                for row in connection.execute(
                    "select name from sqlite_master where type='table'"
                ).fetchall()
            }
            schema_findings = self._check_schema(connection, version, tables)
            findings.extend(schema_findings)
            if not any(finding.fatal for finding in schema_findings):
                findings.extend(self._check_foreign_keys(connection))
                findings.extend(self._check_application_data(connection, tables))
                findings.extend(self._check_downloads(connection, tables))
        except sqlite3.DatabaseError as error:
            findings.append(
                self._finding(
                    "database_unreadable",
                    "Database could not be fully verified: %s" % error,
                    fatal=True,
                )
            )
        finally:
            connection.close()
        return findings

    def _check_schema(self, connection, version, tables):
        findings = []
        if version > self.CURRENT_SCHEMA_VERSION:
            return [
                self._finding(
                    "schema_unsupported",
                    "Database schema version %d is newer than supported version %d."
                    % (version, self.CURRENT_SCHEMA_VERSION),
                    fatal=True,
                )
            ]
        if version < self.CURRENT_SCHEMA_VERSION:
            findings.append(
                self._finding(
                    "schema_outdated",
                    "Database schema version %d should be migrated to version %d."
                    % (version, self.CURRENT_SCHEMA_VERSION),
                    actions=("migrate",),
                )
            )

        expected_tables = set()
        if version > 0 or tables:
            expected_tables.update({"feed", "episode"})
            if version >= 3:
                expected_tables.add("queue")
            if version >= 4:
                expected_tables.add("progress")
            if version >= 5:
                expected_tables.add("download")

        invalid = []
        for table in sorted(expected_tables):
            if table not in tables:
                invalid.append("missing table %s" % table)
                continue
            columns = {
                row[1]: row
                for row in connection.execute("PRAGMA table_info(%s)" % table).fetchall()
            }
            required_columns = set(self.REQUIRED_COLUMNS[table])
            if table == "episode" and version < 2:
                required_columns.discard("played")
            if table == "episode" and version < 6:
                required_columns.discard("guid")
            missing = required_columns - set(columns)
            if missing:
                invalid.append(
                    "%s missing columns %s" % (table, ", ".join(sorted(missing)))
                )
            for column in sorted(required_columns - missing):
                row = columns[column]
                expected_type, expected_not_null, expected_pk, expected_default = (
                    self.COLUMN_DEFINITIONS[table][column]
                )
                if str(row[2]).upper() != expected_type:
                    invalid.append("%s.%s has the wrong declared type" % (table, column))
                if bool(row[3]) != expected_not_null:
                    invalid.append("%s.%s has the wrong nullability" % (table, column))
                if row[5] != expected_pk:
                    invalid.append("%s.%s has the wrong primary-key definition" % (table, column))
                if row[4] != expected_default:
                    invalid.append("%s.%s has the wrong default value" % (table, column))

            required_unique = self.REQUIRED_UNIQUE_COLUMNS.get(table, set())
            if required_unique:
                unique_columns = set()
                for index in connection.execute(
                    "PRAGMA index_list(%s)" % table
                ).fetchall():
                    if not index[2] or index[4]:
                        continue
                    index_columns = tuple(
                        row[2]
                        for row in connection.execute(
                            'PRAGMA index_info("%s")' % index[1].replace('"', '""')
                        ).fetchall()
                    )
                    unique_columns.add(index_columns)
                for column_names in sorted(required_unique - unique_columns):
                    invalid.append(
                        "%s.%s is missing its unique constraint"
                        % (table, ",".join(column_names))
                    )

            required_foreign_keys = self.REQUIRED_FOREIGN_KEYS.get(table, set())
            if required_foreign_keys:
                foreign_key_rows = {}
                for row in connection.execute(
                    "PRAGMA foreign_key_list(%s)" % table
                ).fetchall():
                    foreign_key_rows.setdefault(row[0], []).append(row)
                foreign_keys = {
                    (rows[0][3], rows[0][2], rows[0][4], rows[0][5], rows[0][6])
                    for rows in foreign_key_rows.values()
                    if len(rows) == 1
                }
                for foreign_key in sorted(required_foreign_keys - foreign_keys):
                    invalid.append(
                        "%s.%s is missing its foreign key to %s.%s"
                        % (table, foreign_key[0], foreign_key[1], foreign_key[2])
                    )
        if invalid:
            for finding in findings:
                if finding.code == "schema_outdated":
                    finding.actions = ()
            findings.append(
                self._finding(
                    "schema_invalid",
                    "Database schema is invalid: %s" % "; ".join(invalid),
                    fatal=True,
                )
            )
        return findings

    def _check_foreign_keys(self, connection):
        findings = []
        for table, rowid, parent, constraint in connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall():
            actions = ("delete_row",) if rowid is not None else ()
            findings.append(
                self._finding(
                    "foreign_key_violation",
                    "%s row %s references a missing %s record."
                    % (table, rowid, parent),
                    actions=actions,
                    data={"table": table, "rowid": rowid, "constraint": constraint},
                )
            )
        return findings

    def _check_application_data(self, connection, tables):
        findings = []
        if "feed" in tables:
            rows = connection.execute(
                "select rowid from feed where typeof(key) != 'text' or trim(key) = '' "
                "or typeof(title) != 'text' or trim(title) = ''"
            ).fetchall()
            for (rowid,) in rows:
                findings.append(
                    self._finding(
                        "feed_invalid",
                        "Feed row %s has an invalid key or title." % rowid,
                        actions=("delete_row",),
                        data={"table": "feed", "rowid": rowid},
                    )
                )

        if "episode" in tables:
            episode_columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(episode)").fetchall()
            }
            rows = connection.execute(
                "select rowid from episode where "
                "(coalesce(trim(title), '') = '' and coalesce(trim(description), '') = '')"
            ).fetchall()
            for (rowid,) in rows:
                findings.append(
                    self._finding(
                        "episode_invalid",
                        "Episode row %s has neither a title nor description." % rowid,
                        actions=("delete_row",),
                        data={"table": "episode", "rowid": rowid},
                    )
                )
            if "played" in episode_columns:
                rows = connection.execute(
                    "select rowid from episode where typeof(played) != 'integer' "
                    "or played not in (0, 1)"
                ).fetchall()
                for (rowid,) in rows:
                    findings.append(
                        self._finding(
                            "episode_played_invalid",
                            "Episode row %s has an invalid played value." % rowid,
                            actions=("reset_played",),
                            data={"rowid": rowid},
                        )
                    )

        if "progress" in tables:
            rows = connection.execute(
                "select rowid from progress where typeof(time) != 'integer' or time < 0"
            ).fetchall()
            for (rowid,) in rows:
                findings.append(
                    self._finding(
                        "progress_invalid",
                        "Progress row %s has an invalid playback time." % rowid,
                        actions=("delete_row",),
                        data={"table": "progress", "rowid": rowid},
                    )
                )

        if "queue" in tables:
            positions = [
                row[0]
                for row in connection.execute("select id from queue order by id").fetchall()
            ]
            if positions != list(range(1, len(positions) + 1)):
                findings.append(
                    self._finding(
                        "queue_order_invalid",
                        "Saved queue positions are not contiguous.",
                        actions=("reorder_queue",),
                    )
                )
        return findings

    @staticmethod
    def _legacy_key(relative_path):
        parts = relative_path.parts
        if len(parts) < 2:
            return None
        filename = parts[-1]
        prefix, separator, _remainder = filename.partition("-")
        if not separator or not prefix.isdigit():
            return None
        return (parts[-2], int(prefix))

    def _safe_download_path(self, relative_path):
        if not isinstance(relative_path, str) or "\\" in relative_path:
            return None
        pure_path = PurePosixPath(relative_path)
        if (
            pure_path.is_absolute()
            or not pure_path.parts
            or ".." in pure_path.parts
            or pure_path.name.endswith(".part")
        ):
            return None
        candidate = self.download_dir.joinpath(*pure_path.parts)
        try:
            candidate.resolve().relative_to(self.download_dir.resolve())
        except ValueError:
            return None
        return candidate

    def _files_on_disk(self):
        files = []
        errors = []
        if not self.download_dir.exists():
            return files, errors

        def on_error(error):
            errors.append(error)

        for root, _directories, filenames in os.walk(str(self.download_dir), onerror=on_error):
            for filename in filenames:
                files.append(Path(root) / filename)
        return files, errors

    def _check_downloads(self, connection, tables):
        findings = []
        if "episode" not in tables or "feed" not in tables:
            return findings

        episode_rows = connection.execute(
            "select episode.id, feed.title, episode.title, episode.enclosure "
            "from episode join feed on episode.feed_key = feed.key"
        ).fetchall()
        episodes = {
            (helpers.sanitize_path(str(feed_title)), ep_id): {
                "ep_id": ep_id,
                "feed_title": feed_title,
                "episode_title": episode_title,
                "enclosure": enclosure,
            }
            for ep_id, feed_title, episode_title, enclosure in episode_rows
        }

        tracked = {}
        tracked_by_episode = {}
        if "download" in tables:
            for ep_id, path, checksum in connection.execute(
                "select ep_id, path, sha256 from download"
            ).fetchall():
                absolute_path = self._safe_download_path(path)
                data = {
                    "ep_id": ep_id,
                    "path": path,
                    "absolute_path": absolute_path,
                    "checksum": checksum,
                }
                if absolute_path is None or not self._valid_checksum(checksum):
                    findings.append(
                        self._finding(
                            "download_metadata_invalid",
                            "Episode %s has unsafe or invalid download metadata." % ep_id,
                            actions=("forget",),
                            data=data,
                        )
                    )
                    continue
                relative = PurePosixPath(path)
                tracked[relative.as_posix()] = data
                tracked_by_episode[ep_id] = data
                if not absolute_path.is_file():
                    findings.append(
                        self._finding(
                            "download_missing",
                            "Tracked download is missing: %s" % path,
                            actions=("redownload", "forget"),
                            data=data,
                        )
                    )
                    continue
                try:
                    actual_checksum = self.sha256_file(absolute_path)
                except OSError as error:
                    findings.append(
                        self._finding(
                            "download_unreadable",
                            "Download cannot be read (%s): %s" % (path, error),
                            actions=("redownload", "remove"),
                            data=data,
                        )
                    )
                    continue
                if actual_checksum.lower() != checksum.lower():
                    findings.append(
                        self._finding(
                            "checksum_mismatch",
                            "Download checksum does not match: %s" % path,
                            actions=("redownload", "remove"),
                            data=data,
                        )
                    )

        files, walk_errors = self._files_on_disk()
        for error in walk_errors:
            findings.append(
                self._finding(
                    "download_directory_unreadable",
                    "Download directory cannot be read: %s" % error,
                    fatal=True,
                )
            )

        legacy_counts = {}
        for absolute_path in files:
            try:
                relative_path = absolute_path.relative_to(self.download_dir)
            except ValueError:
                continue
            normalized = PurePosixPath(*relative_path.parts).as_posix()
            try:
                absolute_path.resolve().relative_to(self.download_dir.resolve())
            except ValueError:
                findings.append(
                    self._finding(
                        "download_orphaned",
                        "Unexpected download path escapes the download directory: %s"
                        % normalized,
                        actions=("remove_file",),
                        data={"absolute_path": absolute_path, "path": normalized},
                    )
                )
                continue
            if normalized in tracked:
                continue
            if normalized.endswith(".part"):
                completed_path = normalized[: -len(".part")]
                episode = episodes.get(self._legacy_key(PurePosixPath(completed_path)))
                data = {"absolute_path": absolute_path, "path": completed_path}
                actions = ("remove_file",)
                if episode is not None:
                    data.update(episode)
                    actions = ("redownload", "remove_file")
                findings.append(
                    self._finding(
                        "download_partial",
                        "Incomplete download artifact found: %s" % normalized,
                        actions=actions,
                        data=data,
                    )
                )
                continue
            legacy_key = self._legacy_key(relative_path)
            episode = episodes.get(legacy_key)
            if episode is None:
                findings.append(
                    self._finding(
                        "download_orphaned",
                        "Unexpected download file is not associated with an episode: %s"
                        % normalized,
                        actions=("remove_file",),
                        data={"absolute_path": absolute_path, "path": normalized},
                    )
                )
                continue

            count = legacy_counts.get(legacy_key, 0) + 1
            legacy_counts[legacy_key] = count
            data = dict(episode)
            data.update({"absolute_path": absolute_path, "path": normalized})
            if episode["ep_id"] in tracked_by_episode or count > 1:
                findings.append(
                    self._finding(
                        "download_duplicate",
                        "Episode %s has an extra download file: %s"
                        % (episode["ep_id"], normalized),
                        actions=("remove_file",),
                        data=data,
                    )
                )
            else:
                findings.append(
                    self._finding(
                        "download_legacy",
                        "Download has no trusted checksum: %s" % normalized,
                        actions=("baseline", "redownload", "remove"),
                        data=data,
                    )
                )
        return findings

    @staticmethod
    def _valid_checksum(checksum):
        if not isinstance(checksum, str) or len(checksum) != 64:
            return False
        return all(character in "0123456789abcdefABCDEF" for character in checksum)

    def _ensure_backup(self):
        if self._backup_path is not None:
            return self._backup_path
        timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        base = self.database_path.with_name(
            self.database_path.name + ".verify-backup-" + timestamp
        )
        backup_path = base
        index = 1
        while backup_path.exists():
            backup_path = Path(str(base) + "-%d" % index)
            index += 1

        source = sqlite3.connect(self._database_uri(self.database_path, "ro"), uri=True)
        destination = sqlite3.connect(str(backup_path))
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()
        self._backup_path = backup_path
        return backup_path

    def _write_connection(self):
        connection = sqlite3.connect(
            self._database_uri(self.database_path, "rw"), uri=True
        )
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_backup()
        except Exception:
            connection.rollback()
            connection.close()
            raise
        return connection

    def repair(self, finding, action):
        """Apply one explicitly selected repair action."""
        if action not in finding.actions:
            raise ValueError("Unsupported repair action: %s" % action)
        data = finding.data

        if action == "remove_file":
            path = Path(data["absolute_path"])
            if path.exists():
                path.unlink()
            return

        if action == "migrate":
            connection = self._write_connection()
            try:
                Database.migrate_connection(connection)
            finally:
                connection.close()
            return

        if action in {"delete_row", "reset_played", "reorder_queue", "forget"}:
            connection = self._write_connection()
            try:
                with connection:
                    if action == "delete_row":
                        table = data["table"]
                        if table not in {"feed", "episode", "queue", "progress", "download"}:
                            raise ValueError("Unsafe table name: %s" % table)
                        connection.execute(
                            'delete from "%s" where rowid=?' % table,
                            (data["rowid"],),
                        )
                    elif action == "reset_played":
                        connection.execute(
                            "update episode set played=0 where rowid=?", (data["rowid"],)
                        )
                    elif action == "reorder_queue":
                        episode_ids = [
                            row[0]
                            for row in connection.execute(
                                "select ep_id from queue order by id"
                            ).fetchall()
                        ]
                        connection.execute("delete from queue")
                        connection.executemany(
                            "insert into queue (id, ep_id) values (?, ?)",
                            enumerate(episode_ids, 1),
                        )
                    else:
                        connection.execute(
                            "delete from download where ep_id=?", (data["ep_id"],)
                        )
            finally:
                connection.close()
            return

        if action == "baseline":
            checksum = self.sha256_file(data["absolute_path"])
            self._replace_download_metadata(data["ep_id"], data["path"], checksum)
            return

        if action == "redownload":
            if finding.code == "download_partial":
                partial_path = Path(data["absolute_path"])
                if partial_path.exists():
                    partial_path.unlink()
            self._redownload(data)
            return

        if action == "remove":
            if data.get("checksum") is not None and data.get("ep_id") is not None:
                self._delete_download_metadata(data["ep_id"])
            path = data.get("absolute_path")
            if path is not None and Path(path).exists():
                Path(path).unlink()
            return

        raise ValueError("Unhandled repair action: %s" % action)

    def _replace_download_metadata(self, ep_id, path, checksum):
        connection = self._write_connection()
        try:
            with connection:
                connection.execute(
                    "replace into download (ep_id, path, sha256) values (?, ?, ?)",
                    (ep_id, path, checksum),
                )
        finally:
            connection.close()

    def _delete_download_metadata(self, ep_id):
        connection = self._write_connection()
        try:
            with connection:
                connection.execute("delete from download where ep_id=?", (ep_id,))
        finally:
            connection.close()

    def _redownload(self, data):
        connection = sqlite3.connect(
            self._database_uri(self.database_path, "ro"), uri=True
        )
        try:
            row = connection.execute(
                "select episode.enclosure, episode.title, feed.title from episode "
                "join feed on episode.feed_key=feed.key where episode.id=?",
                (data["ep_id"],),
            ).fetchone()
        finally:
            connection.close()
        if (
            row is None
            or not isinstance(row[0], str)
            or not row[0].startswith(("http://", "https://"))
        ):
            raise ValueError("Episode does not have a downloadable enclosure")

        enclosure, episode_title, feed_title = row
        relative_path = data.get("path")
        if relative_path is None:
            extension = os.path.splitext(enclosure)[1].split("?")[0]
            relative_path = PurePosixPath(
                helpers.sanitize_path(str(feed_title)),
                "%s-%s%s"
                % (data["ep_id"], helpers.sanitize_path(str(episode_title)), extension),
            ).as_posix()
        destination = self._safe_download_path(relative_path)
        if destination is None:
            raise ValueError("Repair destination is unsafe")
        DataFile.ensure_path(str(destination))
        completed = {}

        def on_complete(_path, checksum):
            completed["checksum"] = checksum

        DataFile.download_to_file(
            enclosure,
            destination,
            str(episode_title),
            _RepairDownloadQueue(),
            on_complete=on_complete,
        )
        if "checksum" not in completed:
            raise RuntimeError("Episode redownload failed")
        self._replace_download_metadata(
            data["ep_id"], relative_path, completed["checksum"]
        )


def _default_download_dir():
    configured = Config["custom_download_dir"]
    return download_path(configured, default=DataFile.DEFAULT_DOWNLOADED_DIR)


def _print_findings(findings, output):
    if not findings:
        print("Verification passed: database and downloads are intact.", file=output)
        return
    for finding in findings:
        print("[%s] %s" % (finding.code, finding.message), file=output)
    print("Verification found %d problem(s)." % len(findings), file=output)


def _choose_action(finding, input_func):
    if not finding.actions:
        return None
    if len(finding.actions) == 1:
        action = finding.actions[0]
        answer = input_func(
            "%s? [r]epair/[s]kip: " % Verifier.ACTION_LABELS[action]
        ).strip().lower()
        return action if answer in {"r", "repair", "y", "yes"} else None

    aliases = {
        "b": "baseline",
        "r": "redownload",
        "d": "remove",
        "f": "forget",
        "x": "remove_file",
        "s": None,
    }
    hotkeys = {
        "baseline": "b",
        "redownload": "r",
        "remove": "d",
        "forget": "f",
        "remove_file": "x",
    }
    choices = ", ".join(
        "%s=%s" % (hotkeys[action], Verifier.ACTION_LABELS[action])
        for action in finding.actions
    )
    answer = input_func("Choose repair (%s, s=skip): " % choices).strip().lower()
    if answer in finding.actions:
        return answer
    selected = aliases.get(answer)
    return selected if selected in finding.actions else None


def run_verify(
    database_path=None,
    download_dir=None,
    interactive=None,
    input_func=input,
    output=None,
):
    """Run verification, optionally prompting for repairs, and return an exit code."""
    if database_path is None:
        database_path = Database.PATH
    if download_dir is None:
        download_dir = _default_download_dir()
    if output is None:
        output = sys.stdout
    if interactive is None:
        interactive = sys.stdin.isatty() and sys.stdout.isatty()

    verifier = Verifier(database_path, download_dir)
    findings = verifier.scan()
    _print_findings(findings, output)

    repaired = False
    announced_backup = None
    if interactive:
        for finding in findings:
            action = _choose_action(finding, input_func)
            if action is None:
                continue
            try:
                verifier.repair(finding, action)
                repaired = True
                if (
                    verifier.backup_path is not None
                    and verifier.backup_path != announced_backup
                ):
                    print(
                        "Database backup created: %s" % verifier.backup_path,
                        file=output,
                    )
                    announced_backup = verifier.backup_path
            except (OSError, RuntimeError, sqlite3.DatabaseError, ValueError) as error:
                print("Repair failed for %s: %s" % (finding.code, error), file=output)

    if repaired:
        print("Re-running verification after repairs...", file=output)
        findings = verifier.scan()
        _print_findings(findings, output)
    return 0 if not findings else 1
