# SQLite migration and recovery

Updated: 2026-10-29. Wapas uses SQLite online backup for a consistent snapshot. Application startup initializes new tables, applies the additive schema migration, adds missing columns, and seeds a default merchant/store. This guide does not authorize running startup against a production or populated database without an operator-approved maintenance window.

## Before changing an existing installation

1. Identify the configured SQLite file and its absolute path. Stop writes by putting the application into a maintenance window and stopping the app/worker. Do not inspect or paste `.env` secrets into logs or tickets.
2. Choose a new, dated backup filename that does not already exist. From the project folder, run:

   ```powershell
   .\.venv\Scripts\python.exe -m app.backup_db --source .\wapas.db --destination .\backups\wapas-before-merchant-os-2026-10-29.db
   ```

   Replace the source path with the actual configured database file. The helper uses SQLite's online backup API and verifies the destination with `PRAGMA integrity_check`. It refuses to overwrite an existing destination. Keep the snapshot outside source control with appropriate access controls.
3. Record the source file size, backup path, time, and successful integrity result in the operator's change record. The helper does not verify business-level row counts or Paytm reconciliation.

## Rehearse on a separate copy

Copy the verified backup to a new rehearsal filename; never point a rehearsal at the original database. For example:

```powershell
Copy-Item -NoClobber .\backups\wapas-before-merchant-os-2026-10-29.db .\backups\wapas-merchant-os-rehearsal.db
$env:WAPAS_ENV = "development"
$env:DATABASE_URL = "sqlite:///./backups/wapas-merchant-os-rehearsal.db"
```

Start the app against that rehearsal URL, check startup logs, inspect expected business records and tenant identity, and restart once to check migration idempotency. Then stop the app and run an independent integrity check with Python:

```powershell
.\.venv\Scripts\python.exe -c "import sqlite3; db=sqlite3.connect(r'.\backups\wapas-merchant-os-rehearsal.db'); print(db.execute('PRAGMA integrity_check').fetchone()[0]); db.close()"
```

Compare representative pre/post row counts and totals for payments, cases, customers, and outcomes. The migration must not change historical amounts, provider outcomes, timestamps, or ownership. The current local implementation has tests for migration behavior on fixtures, but no operator rehearsal has been performed against an installation copy.

## Recovery

If the rehearsal fails, stop the app and discard only the clearly identified rehearsal copy after confirming its absolute path. The source database remains the recovery point. To restore, first stop all app and worker processes, preserve the failed database for diagnosis, and copy the verified backup to a new restore filename. Validate `PRAGMA integrity_check` and representative business rows before configuring the app to use that restored file. Never overwrite the only backup or copy a live `.db` file while ignoring its WAL state.

The helper CLI requires both `--source` and `--destination`; `python -m app.backup_db` without arguments is not a valid backup command. A backup is not a migration, and a migration test is not a restore rehearsal.

## Current implementation boundary

The migration code is additive for the legacy single-merchant tables: it creates the default merchant/store, backfills legacy rows with the default merchant, and adds missing columns. SQLite triggers enforce several immutability rules. Tests use temporary databases. No PostgreSQL/MongoDB migration path is provided.

**Data-safety incident, 2026-10-29:** a browser-harness setup error called `db.init_db()` against the protected `D:\Wapas\wapas.db`. The incident, verified outside-project SQLite backup, and narrow account/session containment are documented in [incident-containment-2026-10-30.md](incident-containment-2026-10-30.md). Historical provider/currency values for the 630 affected Payment rows are unknown; their current migration defaults are not payment evidence. The database remains modified and has not been restored or rehearsed. A new engine guard blocks ordinary application access to this exact protected path unless the maintenance override is explicitly set. Tests and browser runs must continue using disposable databases.
