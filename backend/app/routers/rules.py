"""Classification rules — add or update master_rules and reload triage intelligence."""

import json

from fastapi import APIRouter, Depends

from app.database import get_conn
from app.deps import require_write_auth
from app.models import RuleCreate
from app.services import triage_service

router = APIRouter(prefix="/api/v1/rules", tags=["rules"])


@router.post("")
def add_master_rule(
    req: RuleCreate,
    _: None = Depends(require_write_auth),
):
    pattern_json = json.dumps(req.pattern_text, sort_keys=True)
    with get_conn() as conn:
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO master_rules (pattern_text, target_bucket_id, added_by)
                VALUES (%s, %s, %s)
                ON CONFLICT (pattern_text) DO UPDATE SET
                    target_bucket_id = EXCLUDED.target_bucket_id;
                """,
                (pattern_json, req.target_bucket_id, req.added_by),
            )
            triage_service.load_intelligence(conn)
            conn.commit()
        finally:
            cur.close()
    return {"status": "success", "message": "Rule added for future triage."}
