# CLAUDE.md

## Prod writes

Prod is sands.usu.edu (`/opt/macfax`). One session at a time may change it; the prod write lock
(`ops/prod-lock.sh`, `/opt/macfax/.locks/prod`) enforces that, and the nightly holds it too
(holder `nightly`, about 10:00–11:00 UTC).

- **Check first:** `fab lock-status`. If it is held, wait; do not work around it.
- **Deploy only with `fab deploy`.** It takes the lock and refuses while anyone else holds it. No
  manual `git reset` / `docker compose up` on the server.
- **Ad-hoc writes** (data fixes, backfills, one-off `manage.py` commands, SQL that changes rows) run
  through the lock on the server:
  `/opt/macfax/ops/prod-lock.sh run "<you/session>" -- docker compose exec -T backend python manage.py ...`
- **Never break a lock you don't own** (`fab lock-break --yes`) without first checking it is stale:
  read the holder and start time from `fab lock-status`, and confirm that holder's process is gone
  (`docker top macfax-backend-1`, `docker top macfax-scheduler-1`, the holder's session). A lock held
  by `nightly` while the nightly runs is not stale.
- The nightly's results are in the pipeline run log: `fab pipeline-log`.
