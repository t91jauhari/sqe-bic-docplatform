"""Authorized report read models; no artifact creation or release changes."""
from collections import OrderedDict
from dataclasses import dataclass

from sqlalchemy import func, select

from app.db import Case, Report

_MAX_REPORT_SUMMARY_CACHE = 2048


@dataclass(frozen=True)
class ReportAudience:
    organization: str
    branches: tuple[str, ...] | None


def _summary_cache(session) -> OrderedDict | None:
    if session.new or session.dirty or session.deleted:
        return None
    bind = session.get_bind()
    cache = getattr(bind, "_sqe_report_summary_cache", None)
    if cache is None:
        cache = OrderedDict()
        setattr(bind, "_sqe_report_summary_cache", cache)
    return cache


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
        meta_rows = self.session.execute(
            select(
                Report.id,
                Report.case_id,
                Report.version,
                Report.state,
                Report.created_at,
                Report.fingerprint,
                Case.template,
            )
            .join(Case, Case.id == Report.case_id)
            .join(ranked, Report.id == ranked.c.id)
            .where(ranked.c.position == 1)
            .order_by(Report.created_at.desc())
        ).all()
        if not meta_rows:
            return []
        cache = _summary_cache(self.session)
        summaries = {}
        missing_ids = []
        for r_id, _, _, _, _, fp, _ in meta_rows:
            key = (r_id, fp)
            if cache is not None and key in cache:
                cache.move_to_end(key)
                summaries[r_id] = cache[key]
            else:
                missing_ids.append(r_id)
        if missing_ids:
            for r_id, fp, snap in self.session.execute(
                select(Report.id, Report.fingerprint, Report.snapshot).where(
                    Report.id.in_(missing_ids)
                )
            ):
                entry = {
                    'customer': snap['customer'],
                    'validation_status': snap['validation_status'],
                    'provider': snap['provider'],
                    'reference': snap.get('reference', ''),
                }
                summaries[r_id] = entry
                if cache is not None:
                    cache[(r_id, fp)] = entry
                    cache.move_to_end((r_id, fp))
                    while len(cache) > _MAX_REPORT_SUMMARY_CACHE:
                        cache.popitem(last=False)
        return [{
            'id': r_id, 'case_id': case_id, 'version': version,
            'state': state, 'created_at': created_at,
            'customer': summaries[r_id]['customer'],
            'validation_status': summaries[r_id]['validation_status'],
            'provider': summaries[r_id]['provider'],
            'reference': summaries[r_id]['reference'], 'transaction_flow': flow,
        } for r_id, case_id, version, state, created_at, _, flow in meta_rows]
