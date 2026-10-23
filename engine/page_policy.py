"""Physical-page selection shared by document validation and SOP checks."""


def required_initial_pages(count, *, exclude_final_page=False, explicit_pages=None):
    if type(count) is not int or not 1 <= count <= 1000:
        raise ValueError("Physical page count must be an integer from 1 to 1000.")
    if type(exclude_final_page) is not bool:
        raise ValueError("exclude_final_page must be boolean.")
    if exclude_final_page:
        return list(range(1, count))
    pages = list(range(1, count + 1)) if explicit_pages is None else explicit_pages
    if (not isinstance(pages, list) or not pages
            or any(type(n) is not int or not 1 <= n <= count for n in pages)
            or len(set(pages)) != len(pages)):
        raise ValueError("Required initial pages must be unique physical page numbers.")
    return list(pages)


def initial_page_records(count, pages, *, exclude_final_page=False, explicit_pages=None):
    required = required_initial_pages(count, exclude_final_page=exclude_final_page, explicit_pages=explicit_pages)
    if not isinstance(pages, list) or any(
        not isinstance(p, dict) or type(p.get("page_number")) is not int
        or not 1 <= p["page_number"] <= count for p in pages
    ):
        raise ValueError("Page observations must identify valid physical pages.")
    numbers = [p["page_number"] for p in pages]
    coverage = required if exclude_final_page else list(range(1, count + 1))
    if len(set(numbers)) != len(numbers) or not set(coverage) <= set(numbers):
        raise ValueError("Required page observations are missing or duplicated.")
    return [p for p in pages if p["page_number"] in required]
