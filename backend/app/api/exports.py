"""Exports HTTP boundary."""

from fastapi import APIRouter
import csv
import io
from fastapi import Depends, HTTPException, Response
from sqlalchemy import select
from app.db import Document, SessionLocal
from app.native_profiles import LABELS
from app.auditing import audit
from app.configuration.revisions import latest_config
from app.reporting import csv_safe
from app.security import current_user, scoped

router = APIRouter(tags=["exports"])


@router.get("/api/exports/{doc_type}")
def export_csv(doc_type: str, user=Depends(current_user)):
    if doc_type not in LABELS:
        raise HTTPException(404, "Unknown document type.")
    with SessionLocal.begin() as db:
        docs = db.scalars(
            scoped(
                select(Document).where(Document.doc_type == doc_type), Document, user
            ).order_by(Document.created_at)
        ).all()
        columns = list(
            latest_config(db, user.org).payload["profiles"][doc_type]["columns"]
        )
        known = {k for (k, _) in columns}
        for doc in docs:
            for key in doc.normalized:
                if (
                    key not in known
                    and (not key.startswith("_"))
                    and (key != "page_results")
                ):
                    columns.append([key, key])
                    known.add(key)
        stream = io.StringIO(newline="")
        writer = csv.writer(stream)
        writer.writerow(
            [
                "source_file",
                "case_id",
                "branch_id",
                "processing_status",
                "validation_status",
            ]
            + [x[0] for x in columns]
        )
        for d in docs:
            writer.writerow(
                [
                    csv_safe(d.filename),
                    d.case_id,
                    d.branch_id,
                    d.status,
                    d.validation_status,
                ]
                + [csv_safe(d.normalized.get(k)) for (k, _) in columns]
            )
        audit(
            db,
            user.org,
            user.id,
            "export.downloaded",
            document_type=doc_type,
            count=len(docs),
        )
        return Response(
            ("\ufeff" + stream.getvalue()).encode(),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="{doc_type}_result.csv"'
            },
        )
