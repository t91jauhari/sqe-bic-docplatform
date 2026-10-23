"""Authorized report read models; no artifact creation or release changes."""
from dataclasses import dataclass

from sqlalchemy import func, select

from app.db import Case, Report


@dataclass(frozen=True)
class ReportAudience:
    organization: str
    branches: tuple[str, ...] | None


class ReportQueries:
    def __init__(self, session, audience: ReportAudience):
        self.session = session
        self.audience = audience

    def current(self):
        query = select(Report.id.label('id'), func.row_number().over(
            partition_by=(Case.branch_id, Case.template, func.lower(func.trim(Case.customer))),
            order_by=(Report.created_at.desc(), Report.version.desc(), Report.id.desc()),
        ).label('position')).join(Case, Case.id == Report.case_id).where(
            Report.org == self.audience.organization, Case.status != 'MERGED',
        )
        if self.audience.branches is not None:
            query = query.where(Report.branch_id.in_(self.audience.branches))
        ranked = query.subquery()
        rows = self.session.execute(
            select(Report, Case.template).join(Case, Case.id == Report.case_id)
            .join(ranked, Report.id == ranked.c.id).where(ranked.c.position == 1)
            .order_by(Report.created_at.desc())
        )
        return [{
            'id': report.id, 'case_id': report.case_id, 'version': report.version,
            'state': report.state, 'created_at': report.created_at,
            'customer': report.snapshot['customer'],
            'validation_status': report.snapshot['validation_status'],
            'provider': report.snapshot['provider'],
            'reference': report.snapshot.get('reference', ''), 'transaction_flow': flow,
        } for report, flow in rows]
