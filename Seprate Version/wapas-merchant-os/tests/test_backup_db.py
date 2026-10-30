import sqlite3

import pytest

from app.backup_db import backup_database


def test_sqlite_backup_includes_committed_wal_and_refuses_overwrite(tmp_path):
    source = tmp_path / "source database.db"
    destination = tmp_path / "backup" / "snapshot.db"
    connection = sqlite3.connect(source)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("CREATE TABLE facts (value TEXT NOT NULL)")
    connection.execute("INSERT INTO facts VALUES ('committed')")
    connection.commit()

    result = backup_database(source, destination)
    assert result == destination.resolve()
    backup = sqlite3.connect(destination)
    assert backup.execute("SELECT value FROM facts").fetchone() == ("committed",)
    assert backup.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    backup.close()

    with pytest.raises(FileExistsError):
        backup_database(source, destination)
    connection.close()
