"""Report selection only; keep source cases and frozen report snapshots intact."""
from datetime import datetime
from .db import Case
from .sop import value_at


def transaction_date(snapshot):
    docs = snapshot.get("documents", [])
    for path in ("application.transaction_date", "account_opening_form.transaction_date"):
        value, _ = value_at(docs, path)
        if isinstance(value, dict):
            value = value.get("raw", value.get("value"))
        if not isinstance(value,str):
            continue
        kind = path.split(".")[0]
        day_first = snapshot.get("configuration",{}).get("profiles",{}).get(kind,{}).get("policy",{}).get("day_first",True)
        for fmt in ("%Y-%m-%d", "%d-%m-%Y" if day_first else "%m-%d-%Y", "%d/%m/%Y" if day_first else "%m/%d/%Y"):
            try:
                return datetime.strptime(value.strip(),fmt).date()
            except ValueError:
                pass
    return None


def select_branch_reports(db, reports, flow=None, date_from=None, date_to=None):
    # First freeze one current version per case, then filter the transaction
    # period. Never recover an older report version just to match the dates.
    per_case = {}
    for report in reports:
        previous=per_case.get(report.case_id)
        if not previous or (report.version,report.created_at,report.id) > (previous.version,previous.created_at,previous.id):
            per_case[report.case_id]=report
    customers={}
    for report in per_case.values():
        case=db.get(Case,report.case_id)
        if not case or case.status=="MERGED" or flow and case.template!=flow:
            continue
        if date_from or date_to:
            day=transaction_date(report.snapshot)
            if day is None or date_from and day<date_from or date_to and day>date_to:
                continue
        key=(case.customer.strip().casefold(),case.template)
        previous=customers.get(key)
        if not previous or (report.created_at,report.version,report.id) > (previous.created_at,previous.version,previous.id):
            customers[key]=report
    return dict(sorted(customers.items()))


def export_period(start,end):
    if start and end:
        return f"{start:%d %b %Y} – {end:%d %b %Y} (transaction dates)"
    if start:
        return f"From {start:%d %b %Y} (transaction dates)"
    if end:
        return f"Through {end:%d %b %Y} (transaction dates)"
    return "All transaction dates (unfiltered)"
