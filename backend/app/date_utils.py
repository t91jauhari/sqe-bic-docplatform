"""Robust flexible date parsing supporting multiple formats and conventions."""

from datetime import date, datetime
import re


ID_MONTHS = {
    "januari": "January",
    "februari": "February",
    "maret": "March",
    "april": "April",
    "mei": "May",
    "juni": "June",
    "juli": "July",
    "agustus": "August",
    "september": "September",
    "oktober": "October",
    "november": "November",
    "desember": "December",
    "jan": "Jan",
    "feb": "Feb",
    "mar": "Mar",
    "apr": "Apr",
    "jun": "Jun",
    "jul": "Jul",
    "agu": "Aug",
    "ags": "Aug",
    "sep": "Sep",
    "okt": "Oct",
    "nov": "Nov",
    "des": "Dec",
}


def parse_flexible_date(value, day_first=True, pivot=49):
    """Parse dates in ISO (YYYY-MM-DD, YYYY/MM/DD), day-first (DD-MM-YYYY, DD/MM/YYYY),
    Indonesian/English named months, or timestamps into a standard datetime.date object.
    Raises ValueError on missing, invalid, or impossible dates.
    """
    if value is None:
        raise ValueError("MISSING_DATE")
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    while isinstance(value, dict):
        key = next((k for k in ("raw", "value", "text") if k in value), None)
        if key is None:
            raise ValueError("INVALID_DATE")
        value = value[key]

    s = str(value).strip()
    if not s or s.casefold() in {"", "missing", "null", "none", "n/a", "[blank]", "-"}:
        raise ValueError("MISSING_DATE")

    # If ISO timestamp like "2025-07-01T00:00:00" or "2025-07-01 12:00:00"
    if "T" in s:
        s = s.split("T")[0].strip()
    elif " " in s and ":" in s:
        s = s.split(" ")[0].strip()

    # Normalize Indonesian month names
    s_sub = re.sub(
        r"\b[A-Za-z]+\b",
        lambda m: ID_MONTHS.get(m.group(0).lower(), m.group(0)),
        s,
    )
    s_clean = re.sub(r"\s*([/.-])\s*", r"\1", s_sub).strip()

    # 1. ISO format: YYYY-MM-DD, YYYY/MM/DD, YYYY.MM.DD
    m_iso = re.fullmatch(r"(\d{4})[/.-](\d{1,2})[/.-](\d{1,2})", s_clean)
    if m_iso:
        y, m, d = int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3))
        return date(y, m, d)

    # 2. DD-MM-YYYY or MM-DD-YYYY or DD/MM/YY
    m_numeric = re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{2}|\d{4})", s_clean)
    if m_numeric:
        p1, p2, p3 = int(m_numeric.group(1)), int(m_numeric.group(2)), int(m_numeric.group(3))
        y = p3 if p3 >= 100 else (2000 + p3 if p3 <= pivot else 1900 + p3)
        d, m = (p1, p2) if day_first else (p2, p1)
        # Disambiguate if one exceeds 12
        if d > 31 or m > 12:
            if p2 <= 12 and p1 <= 31:
                d, m = p1, p2
            elif p1 <= 12 and p2 <= 31:
                d, m = p2, p1
        return date(y, m, d)

    # 3. Textual dates like "01 July 2025", "July 1, 2025", "1-Juli-2025"
    from dateutil.parser import parse as parse_datetime

    parsed = parse_datetime(
        s_sub, dayfirst=day_first, fuzzy=False, default=datetime(1, 1, 1)
    )
    return parsed.date()


def compare_dates(actual, expected, op="date_equal", day_first=True):
    """Compare two date representations regardless of separator or ISO vs local format."""
    a = parse_flexible_date(actual, day_first=day_first)
    b = parse_flexible_date(expected, day_first=day_first)
    if op == "date_equal":
        return a == b
    if op == "date_on_or_after":
        return a >= b
    if op == "date_on_or_before":
        return a <= b
    if op == "date_after":
        return a > b
    if op == "date_before":
        return a < b
    raise ValueError(f"Unsupported date comparison operator: {op}")
