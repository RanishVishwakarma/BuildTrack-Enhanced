"""Indexes for the collections added by the RBAC and AI phases.

create_index is idempotent, so this runs on every startup. Unique indexes
back the idempotency guarantees (one project assignment per user/project, one
voice call per alert).
"""

import logging

logger = logging.getLogger(__name__)


async def ensure_indexes(db) -> None:
    specs = [
        ("user_project_access", [("user_id", 1), ("project_id", 1)], {"unique": True}),
        ("user_project_access", [("project_id", 1)], {}),
        ("audit_logs", [("timestamp", -1)], {}),
        ("audit_logs", [("actor_id", 1), ("timestamp", -1)], {}),
        ("audit_logs", [("event_type", 1), ("timestamp", -1)], {}),
        ("ai_conversations", [("user_id", 1), ("updated_at", -1)], {}),
        ("ai_usage", [("user_id", 1), ("at", -1)], {}),
        ("ai_recommendations", [("dedup_key", 1), ("status", 1)], {}),
        ("ai_recommendations", [("project_id", 1), ("status", 1)], {}),
        ("risk_assessments", [("project_id", 1), ("rule", 1)], {"unique": True}),
        ("alerts", [("dedup_key", 1), ("status", 1)], {}),
        ("alerts", [("user_id", 1), ("status", 1)], {}),
        ("job_runs", [("started_at", -1)], {}),
        ("voice_calls", [("alert_id", 1)], {"unique": True}),
        ("voice_calls", [("status", 1), ("next_attempt_at", 1)], {}),
        ("progress_evidence", [("project_id", 1), ("created_at", -1)], {}),
        ("progress_evidence", [("project_id", 1), ("sha256", 1)], {}),
        ("suggestions", [("submitted_by", 1)], {}),
        ("suggestions", [("project_id", 1), ("status", 1)], {}),
        ("safety_reports", [("project_id", 1), ("status", 1)], {}),
        ("corrective_actions", [("assignee_id", 1), ("status", 1)], {}),
        ("generated_reports", [("project_id", 1), ("created_at", -1)], {}),
        ("inventory_reservations", [("item_id", 1), ("status", 1)], {}),
    ]
    for collection, keys, options in specs:
        try:
            await db[collection].create_index(keys, **options)
        except Exception as error:  # e.g. existing duplicate data for a unique index
            logger.warning("Index on %s %s not created: %s", collection, keys, error)
