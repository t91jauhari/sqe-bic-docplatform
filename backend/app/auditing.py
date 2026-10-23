"""Auditing operations."""

import json
from decimal import Decimal
from app.db import Audit


def serial(value):
    return json.loads(
        json.dumps(
            value,
            default=lambda x: format(x, "f") if isinstance(x, Decimal) else str(x),
        )
    )


def audit(db, org, actor, event, branch_id=None, case_id=None, **details):
    db.add(
        Audit(
            org=org,
            actor=actor,
            event=event,
            branch_id=branch_id,
            case_id=case_id,
            details=serial(details),
        )
    )
