"""Create a consistent SQLite snapshot with SQLite's online backup API."""
import argparse
import sqlite3
from pathlib import Path


def backup_database(source_path: str | Path, destination_path: str | Path) -> Path:
    source = Path(source_path).expanduser().resolve()
    destination = Path(destination_path).expanduser().resolve()
    if not source.is_file():
        raise ValueError("Source database file does not exist")
    if source == destination:
        raise ValueError("Backup destination must be different from the source")
    if destination.exists():
        raise FileExistsError("Backup destination already exists; choose a new dated filename")
    destination.parent.mkdir(parents=True, exist_ok=True)
    target_created = False
    source_db = target_db = None
    try:
        source_db = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=10)
        target_db = sqlite3.connect(str(destination), timeout=10)
        target_created = True
        source_db.backup(target_db)
        result = target_db.execute("PRAGMA integrity_check").fetchone()
        if not result or result[0] != "ok":
            raise sqlite3.DatabaseError("Backup integrity check failed")
        target_db.close()
        source_db.close()
        return destination
    except Exception:
        if target_db is not None:
            target_db.close()
        if source_db is not None:
            source_db.close()
        if target_created and destination.exists():
            destination.unlink()
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a consistent SQLite backup without copying WAL files by hand")
    parser.add_argument("--source", required=True, help="SQLite database file to snapshot")
    parser.add_argument("--destination", required=True, help="New backup path; it must not already exist")
    args = parser.parse_args(argv)
    try:
        destination = backup_database(args.source, args.destination)
    except (OSError, ValueError, sqlite3.Error) as exc:
        parser.error(str(exc))
    print(f"SQLite backup created and integrity-checked: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
