"""Shared, conservative job filters. Employer reputation is never inferred."""
import re

from sqlalchemy import and_, not_, or_

from .models import Item

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
