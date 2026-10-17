# BuildTrack Backend

FastAPI + MongoDB (Motor) API for BuildTrack. Setup steps are in the [root README](../README.md).

- `app/core/`: settings, the seven roles, permissions, project access, audit log
- `app/modules/`: feature routers: auth, projects, tasks, workforce, inventory, procurement, reports, the Site Assistant (`ai`), operations intelligence (`intelligence`), monitoring, evidence, hub, actions (approvals), voice, access
- `scripts/setup_database.py`: indexes and the first admin account for a new database
- `scripts/migrate_roles.py`: converts legacy role values. Dry run by default
- `tests/`: `python -m pytest`, run against an in-memory MongoDB

Configuration: copy `.env.example` to `.env`.
