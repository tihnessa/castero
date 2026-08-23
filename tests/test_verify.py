import hashlib
import io
import os
from pathlib import Path
import sqlite3
from unittest import mock

from castero.database import Database
from castero.verify import Verifier, run_verify


def create_database(path, version=5):
    connection = sqlite3.connect(str(path))
    for migration in sorted(os.listdir(Database.MIGRATIONS_DIR)):
        if int(migration.split("-")[0]) > version:
            continue
        with open(os.path.join(Database.MIGRATIONS_DIR, migration), "rt") as migration_file:
            connection.executescript(migration_file.read())
    connection.execute(
        "insert into feed (key, title, description, link, last_build_date, copyright) "
        "values (?, ?, ?, ?, ?, ?)",
        ("https://example.com/feed.xml", "Feed title", "Description", None, None, None),
    )
    connection.execute(
        "insert into episode "
        "(id, feed_key, title, description, link, pubdate, copyright, enclosure, played) "
        "values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            1,
            "https://example.com/feed.xml",
            "Episode title",
            "Description",
            None,
            None,
            None,
            "https://example.com/episode.mp3",
            0,
        ),
    )
    connection.commit()
    connection.close()


def finding_codes(findings):
    return [finding.code for finding in findings]


def test_verifier_accepts_clean_database(tmp_path):
    database_path = tmp_path / "castero.db"
    download_dir = tmp_path / "downloaded"
    download_dir.mkdir()
    create_database(database_path)

    assert Verifier(database_path, download_dir).scan() == []


def test_verifier_does_not_create_missing_database(tmp_path):
    database_path = tmp_path / "missing.db"

    findings = Verifier(database_path, tmp_path / "downloaded").scan()

    assert finding_codes(findings) == ["database_missing"]
    assert not database_path.exists()


def test_verifier_does_not_migrate_database_during_scan(tmp_path):
    database_path = tmp_path / "castero.db"
    create_database(database_path, version=4)
    before = database_path.read_bytes()

    findings = Verifier(database_path, tmp_path / "downloaded").scan()

    assert finding_codes(findings) == ["schema_outdated"]
    assert database_path.read_bytes() == before
    connection = sqlite3.connect(str(database_path))
    assert connection.execute("pragma user_version").fetchone()[0] == 4
    connection.close()


def test_interactive_schema_migration_creates_backup(tmp_path):
    database_path = tmp_path / "castero.db"
    create_database(database_path, version=4)

    output = io.StringIO()
    status = run_verify(
        database_path=database_path,
        download_dir=tmp_path / "downloaded",
        interactive=True,
        input_func=lambda _prompt: "r",
        output=output,
    )

    assert status == 0, output.getvalue()
    connection = sqlite3.connect(str(database_path))
    assert connection.execute("pragma user_version").fetchone()[0] == 5
    connection.close()
    assert list(tmp_path.glob("castero.db.verify-backup-*"))


def test_verifier_reports_unreadable_sqlite_file(tmp_path):
    database_path = tmp_path / "castero.db"
    database_path.write_bytes(b"not a sqlite database")

    findings = Verifier(database_path, tmp_path / "downloaded").scan()

    assert finding_codes(findings) == ["database_unreadable"]


def test_verifier_reports_foreign_key_violation(tmp_path):
    database_path = tmp_path / "castero.db"
    create_database(database_path)
    connection = sqlite3.connect(str(database_path))
    connection.execute("insert into progress (ep_id, time) values (999, 10)")
    connection.commit()
    connection.close()

    findings = Verifier(database_path, tmp_path / "downloaded").scan()

    assert "foreign_key_violation" in finding_codes(findings)


def test_verifier_checks_download_checksum(tmp_path):
    database_path = tmp_path / "castero.db"
    download_dir = tmp_path / "downloaded"
    episode_path = download_dir / "Feed_title" / "1-Episode_title.mp3"
    episode_path.parent.mkdir(parents=True)
    episode_path.write_bytes(b"changed audio")
    create_database(database_path)
    connection = sqlite3.connect(str(database_path))
    connection.execute(
        "insert into download (ep_id, path, sha256) values (?, ?, ?)",
        (1, "Feed_title/1-Episode_title.mp3", hashlib.sha256(b"original audio").hexdigest()),
    )
    connection.commit()
    connection.close()

    findings = Verifier(database_path, download_dir).scan()

    assert "checksum_mismatch" in finding_codes(findings)


def test_verifier_reports_missing_tracked_download(tmp_path):
    database_path = tmp_path / "castero.db"
    create_database(database_path)
    connection = sqlite3.connect(str(database_path))
    connection.execute(
        "insert into download (ep_id, path, sha256) values (?, ?, ?)",
        (1, "Feed_title/1-Episode_title.mp3", "0" * 64),
    )
    connection.commit()
    connection.close()

    findings = Verifier(database_path, tmp_path / "downloaded").scan()

    assert "download_missing" in finding_codes(findings)


def test_verifier_reports_legacy_and_orphaned_downloads(tmp_path):
    database_path = tmp_path / "castero.db"
    download_dir = tmp_path / "downloaded"
    feed_dir = download_dir / "Feed_title"
    feed_dir.mkdir(parents=True)
    (feed_dir / "1-Episode_title.mp3").write_bytes(b"legacy audio")
    (download_dir / "orphan.mp3").write_bytes(b"orphan audio")
    create_database(database_path)

    findings = Verifier(database_path, download_dir).scan()

    assert sorted(finding_codes(findings)) == ["download_legacy", "download_orphaned"]


def test_verifier_reports_duplicate_download(tmp_path):
    database_path = tmp_path / "castero.db"
    download_dir = tmp_path / "downloaded"
    feed_dir = download_dir / "Feed_title"
    feed_dir.mkdir(parents=True)
    (feed_dir / "1-Episode_title.mp3").write_bytes(b"first")
    (feed_dir / "1-Old_title.mp3").write_bytes(b"second")
    create_database(database_path)

    findings = Verifier(database_path, download_dir).scan()

    assert sorted(finding_codes(findings)) == ["download_duplicate", "download_legacy"]


def test_verifier_rejects_unsafe_download_metadata(tmp_path):
    database_path = tmp_path / "castero.db"
    create_database(database_path)
    connection = sqlite3.connect(str(database_path))
    connection.execute(
        "insert into download (ep_id, path, sha256) values (?, ?, ?)",
        (1, "../episode.mp3", "a" * 64),
    )
    connection.commit()
    connection.close()

    findings = Verifier(database_path, tmp_path / "downloaded").scan()

    assert "download_metadata_invalid" in finding_codes(findings)


def test_noninteractive_verification_is_report_only(tmp_path):
    database_path = tmp_path / "castero.db"
    download_dir = tmp_path / "downloaded"
    download_dir.mkdir()
    (download_dir / "orphan.mp3").write_bytes(b"orphan audio")
    create_database(database_path)
    output = io.StringIO()

    status = run_verify(
        database_path=database_path,
        download_dir=download_dir,
        interactive=False,
        output=output,
    )

    assert status == 1
    assert "orphan" in output.getvalue().lower()
    assert (download_dir / "orphan.mp3").exists()


def test_interactive_repair_can_remove_orphan(tmp_path):
    database_path = tmp_path / "castero.db"
    download_dir = tmp_path / "downloaded"
    download_dir.mkdir()
    orphan = download_dir / "orphan.mp3"
    orphan.write_bytes(b"orphan audio")
    create_database(database_path)

    status = run_verify(
        database_path=database_path,
        download_dir=download_dir,
        interactive=True,
        input_func=lambda _prompt: "r",
        output=io.StringIO(),
    )

    assert status == 0
    assert not orphan.exists()


def test_interactive_repair_can_baseline_legacy_download(tmp_path):
    database_path = tmp_path / "castero.db"
    download_dir = tmp_path / "downloaded"
    episode_path = download_dir / "Feed_title" / "1-Episode_title.mp3"
    episode_path.parent.mkdir(parents=True)
    episode_path.write_bytes(b"legacy audio")
    create_database(database_path)

    status = run_verify(
        database_path=database_path,
        download_dir=download_dir,
        interactive=True,
        input_func=lambda _prompt: "b",
        output=io.StringIO(),
    )

    assert status == 0
    connection = sqlite3.connect(str(database_path))
    row = connection.execute("select path, sha256 from download where ep_id=1").fetchone()
    connection.close()
    assert row == (
        "Feed_title/1-Episode_title.mp3",
        hashlib.sha256(b"legacy audio").hexdigest(),
    )
    assert list(tmp_path.glob("castero.db.verify-backup-*"))


@mock.patch("castero.datafile.Net.Get")
def test_interactive_repair_can_redownload_checksum_mismatch(get, tmp_path):
    response = mock.MagicMock()
    response.iter_content.return_value = [b"replacement ", b"audio"]
    get.return_value = response
    database_path = tmp_path / "castero.db"
    download_dir = tmp_path / "downloaded"
    episode_path = download_dir / "Feed_title" / "1-Episode_title.mp3"
    episode_path.parent.mkdir(parents=True)
    episode_path.write_bytes(b"damaged audio")
    create_database(database_path)
    connection = sqlite3.connect(str(database_path))
    connection.execute(
        "insert into download (ep_id, path, sha256) values (?, ?, ?)",
        (
            1,
            "Feed_title/1-Episode_title.mp3",
            hashlib.sha256(b"original audio").hexdigest(),
        ),
    )
    connection.commit()
    connection.close()

    output = io.StringIO()
    status = run_verify(
        database_path=database_path,
        download_dir=download_dir,
        interactive=True,
        input_func=lambda _prompt: "r",
        output=output,
    )

    assert status == 0, output.getvalue()
    assert episode_path.read_bytes() == b"replacement audio"
    connection = sqlite3.connect(str(database_path))
    checksum = connection.execute(
        "select sha256 from download where ep_id=1"
    ).fetchone()[0]
    connection.close()
    assert checksum == hashlib.sha256(b"replacement audio").hexdigest()


def test_legacy_file_can_be_removed_without_migrating_old_schema(tmp_path):
    database_path = tmp_path / "castero.db"
    download_dir = tmp_path / "downloaded"
    episode_path = download_dir / "Feed_title" / "1-Episode_title.mp3"
    episode_path.parent.mkdir(parents=True)
    episode_path.write_bytes(b"legacy audio")
    create_database(database_path, version=4)
    answers = iter(["s", "d"])
    output = io.StringIO()

    status = run_verify(
        database_path=database_path,
        download_dir=download_dir,
        interactive=True,
        input_func=lambda _prompt: next(answers),
        output=output,
    )

    assert status == 1
    assert not episode_path.exists()
    assert "Repair failed" not in output.getvalue()


def test_database_repair_creates_backup(tmp_path):
    database_path = tmp_path / "castero.db"
    create_database(database_path)
    connection = sqlite3.connect(str(database_path))
    connection.execute("insert into progress (ep_id, time) values (999, 10)")
    connection.commit()
    connection.close()

    output = io.StringIO()
    status = run_verify(
        database_path=database_path,
        download_dir=tmp_path / "downloaded",
        interactive=True,
        input_func=lambda _prompt: "r",
        output=output,
    )

    assert status == 0
    assert list(tmp_path.glob("castero.db.verify-backup-*"))
    assert "Database backup created:" in output.getvalue()


def test_verifier_uses_custom_download_directory(tmp_path):
    database_path = tmp_path / "castero.db"
    custom_dir = tmp_path / "custom" / "podcasts"
    episode_path = custom_dir / "Feed_title" / "1-Episode_title.mp3"
    episode_path.parent.mkdir(parents=True)
    content = b"downloaded audio"
    episode_path.write_bytes(content)
    create_database(database_path)
    connection = sqlite3.connect(str(database_path))
    connection.execute(
        "insert into download (ep_id, path, sha256) values (?, ?, ?)",
        (1, "Feed_title/1-Episode_title.mp3", hashlib.sha256(content).hexdigest()),
    )
    connection.commit()
    connection.close()

    assert Verifier(database_path, custom_dir).scan() == []
