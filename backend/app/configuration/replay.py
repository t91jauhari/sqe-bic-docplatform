"""Read-only replay of stored observations against an unpublished configuration."""
from sqlalchemy import select

from app.db import Case, Document
from app.provider import validate_extraction


def replay_configuration(db, *, organization, payload):
    docs = db.scalars(
        select(Document)
        .where(Document.org == organization, Document.status == "COMPLETED")
        .order_by(Document.created_at.desc())
        .limit(20)
    ).all()
    results = []
    for d in docs:
        try:
            response = {
                "extract_result": d.raw,
                "extract_metadata": d.metadata_json,
                "id": d.provider_state.get("extract_job_id"),
            }
            result = validate_extraction(d, payload, response)
            results.append(
                {
                    "filename": d.filename,
                    "batch_id": d.batch_id,
                    "before": d.validation_status,
                    "after": result["status"],
                    "issues": sum(
                        len(x["issues"]) for x in result["fields"].values()
                    ),
                }
            )
        except Exception as exc:
            results.append(
                {
                    "filename": d.filename,
                    "before": d.validation_status,
                    "after": "ERROR",
                    "error": type(exc).__name__,
                }
            )
    from app.case_processing import inputs
    from app.sop import evaluate

    sop_results = []
    for c in db.scalars(
        select(Case)
        .where(Case.org == organization)
        .order_by(Case.updated_at.desc())
        .limit(20)
    ):
        frozen = inputs(db, c)
        from app.transaction_flows import scope_configuration, score_configuration

        scoped_cfg = scope_configuration(payload, c.template)
        findings = evaluate(frozen["documents"], scoped_cfg, frozen["case_context"])
        from app.sop_scoring import point_summary
        from app.forex_sop import package_summary
        sop_results.append(
            {
                "case_id": c.id,
                "customer": c.customer,
                "scores": score_configuration(scoped_cfg, c.template, findings),
                "sop_summary": point_summary(findings),
                "sop_packages": package_summary(findings),
                "findings": findings,
            }
        )
    return {
        "sop_results": sop_results,
        "tested": len(results),
        "results": results,
        "note": "Read-only replay of stored extraction. No cloud jobs or existing case changes.",
    }
