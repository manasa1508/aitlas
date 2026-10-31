"""Shared, conservative job filters. Employer reputation is never inferred."""
import re
from urllib.parse import urlencode

from sqlalchemy import and_, not_, or_

from .models import Item

JOB_SOURCE_KINDS = ("greenhouse_jobs", "smartrecruiters", "lever_jobs")

CITY_ALIASES = {"hyderabad": ("hyderabad",), "bengaluru": ("bengaluru", "bangalore"), "pune": ("pune",), "chennai": ("chennai", "madras")}


def target_location(value: str) -> bool:
    lower = value.lower()
    return not any(word in lower for word in ("pakistan", "sindh")) and any(re.search(r"\b" + alias + r"\b", lower) for aliases in CITY_ALIASES.values() for alias in aliases)


def ai_related(title: str, department: str = "") -> bool:
    # Company-wide AI boilerplate does not make every vacancy an AI role.
    return bool(re.search(r"\b(?:ai|ml|llm|llms|nlp|rag|mlops|genai)\b|machine learning|artificial intelligence|data scien(?:ce|tist)|deep learning|computer vision|generative|agentic|applied scientist|inference|model training", f"{title} {department}", re.I))


def city_condition(city: str):
    location = Item.details["location"].as_string()
    aliases = ("india",) if city == "india" else CITY_ALIASES.get(city, ())
    if city in {"target", "india"}:
        aliases += tuple(alias for group in CITY_ALIASES.values() for alias in group)
    return and_(or_(*(location.ilike(f"%{alias}%") for alias in aliases)), not_(location.ilike("%pakistan%")), not_(location.ilike("%sindh%")))


def apply_job_filters(stmt, city: str, company: str = "", ai_only: bool = False):
    if city != "all":
        stmt = stmt.where(Item.kind == "job", city_condition(city))
    if company:
        stmt = stmt.where(Item.details["company"].as_string() == company)
    if ai_only:
        stmt = stmt.where(Item.details["ai_related"].as_boolean().is_(True))
    return stmt


def job_search_links(city: str, query: str = "", role: str = "all", ai_only: bool = False) -> dict:
    locations = {"hyderabad": ("Hyderabad, Telangana, India", "hyderabad"), "bengaluru": ("Bengaluru, Karnataka, India", "bangalore"), "pune": ("Pune, Maharashtra, India", "pune"), "chennai": ("Chennai, Tamil Nadu, India", "chennai")}
    selected = {city: locations[city]} if city in locations else locations
    hint = {"Research & AI": "machine learning", "Engineering": "software engineer", "Product & design": "product design", "Business & operations": "business operations"}.get(role, "")
    keywords = " ".join(value for value in (query.strip(), hint, "AI" if ai_only else "") if value).strip()
    slug = re.sub(r"[^a-z0-9]+", "-", keywords.lower()).strip("-")
    searches = []
    for key, (label, path_city) in selected.items():
        naukri_path = f"{slug}-jobs-in-{path_city}" if slug else f"jobs-in-{path_city}"
        searches.append({"city": key, "location": label, "keywords": keywords, "links": [
            {"name": "LinkedIn", "url": "https://www.linkedin.com/jobs/search/?" + urlencode({"keywords": keywords, "location": label, "f_TPR": "r604800", "sortBy": "DD"})},
            {"name": "Indeed", "url": "https://in.indeed.com/jobs?" + urlencode({"q": keywords, "l": label, "fromage": 7, "sort": "date"})},
            {"name": "Naukri", "url": f"https://www.naukri.com/{naukri_path}"},
            {"name": "Foundit", "url": f"https://www.foundit.in/search/{naukri_path}"},
        ]})
    return {"searches": searches, "coverage": "External search links only. Results are not downloaded or indexed by AItlas. City and keyword hints are passed to providers; refine their filters there. Global/India views use the four priority cities."}
