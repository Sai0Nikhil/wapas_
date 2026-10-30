# Protected SQLite setup incident and containment

Updated: 2026-10-30 (Asia/Kolkata)

## Incident

During the 2026-10-29 Counter browser-harness setup, the child server used a temporary database, but the parent process imported Wapas settings before inheriting the temporary `DATABASE_URL`. The parent then ran `db.init_db()` against `D:\Wapas\wapas.db`.

The initializer added 12 newer `Payment` columns and backfilled `store_id` on the 630 existing payment rows. The new `provider`, `currency`, and `source_type` values now show defaults (`fake`, `INR`, and `RECOVERY`); they do not establish what the historical provider or currency were. Do not relabel these records or use their present defaults as payment evidence. The initializer also ran normal table, index, and trigger setup. The database WAL was modified and no before-image existed for those changes.

The setup created one `counter-browser-smoke` user, its sole OWNER membership for `merchant_default` / `store_default`, and one session. The harness had previously used a fixed test password. The account was not part of the original merchant installation.

## Backup and containment performed

Before changing account state, a consistent SQLite online backup was created from the database file and WAL state. It was saved outside the project at:

`%LOCALAPPDATA%\Wapas\incident-backups\wapas-pre-containment-2026-10-30.db`

The backup passed SQLite `PRAGMA integrity_check` (`ok`), and independent read-only checks matched the source counts: 630 payments, one user, one membership, one session, and one migration record. The backup SHA-256 is `c22414775b13b2ecd7e0595c8aa59dcfa76a8cb8343ad3df985b98eeb7104a4f`.

After verifying that backup, a parameterized SQLite transaction changed only the harness account’s authentication state: its one unrevoked session was revoked at `2026-10-29T18:36:37.515519+00:00`, and its user and membership were deactivated. The rows were preserved; no account, membership, session, payment, or ledger row was deleted. A post-change read confirmed zero unrevoked sessions and inactive user/membership. A SHA-256 digest of all 630 `Payment` rows matched the verified backup before and after containment.

The historical payment metadata remains uncertain. No payment rows or ledger records were edited, restored, or relabeled. The backup is a recovery point, not proof that the original database can be safely rolled back; there was no pre-incident snapshot to restore.

## Preventive changes

- The corrected browser harness assigns and asserts the disposable database path in both parent and child processes before application imports.
- ORM engine creation now refuses the protected `D:\Wapas\wapas.db` path unless the operator explicitly sets `WAPAS_ALLOW_PROTECTED_DB_WRITES=true` for a planned maintenance action.
- The example environment now points to `wapas-development.db`, and SQLite databases, sidecars, backups, and common credential files are ignored by Git.
- The protected database was not used for tests or application initialization during this sprint. Future migrations still require an explicit backup, rehearsal on a separate copy, and a recovery procedure.

## Remaining verification

The database backup has not been restored or used for a migration rehearsal. Historical provider/currency values cannot be reconstructed from the current database alone. The local Uvicorn process discovered during this sprint was left running; its `/login` path returned 404, so it could not be confirmed as this build. No deployment or production payment was initiated.
