"""Review-gated content import. Only an operator with shell access can publish records."""
import argparse
import json
import re
from pathlib import Path

from sqlalchemy.orm import Session

from .db import SessionLocal
from .models import Company, Evidence, Knowledge, Opportunity, UseCase
from .sources import validate_url

KINDS = {
    "knowledge": (Knowledge, {"id", "title", "year", "category", "summary", "source_url", "source_label"}),
    "company": (Company, {"id", "name", "industry", "summary", "website"}),
    "evidence": (Evidence, {"id", "company_id", "title", "claim", "source_url", "source_label"}),
    "use_case": (UseCase, {"id", "title", "industry", "domain", "summary", "outcome", "evidence_url", "evidence_label", "maturity"}),
    "opportunity": (Opportunity, {"id", "title", "industry", "capability", "thesis", "barrier", "evidence_url", "evidence_label"}),
}


def import_records(session: Session, records: list[dict]) -> int:
    if not isinstance(records, list) or len(records) > 500:
        raise ValueError("Input must be a list of at most 500 records")
    for index, raw in enumerate(records):
        if not isinstance(raw, dict) or raw.get("type") not in KINDS:
            raise ValueError(f"Record {index}: unknown type")
        kind = raw["type"]
        model, required = KINDS[kind]
        data = {key: value for key, value in raw.items() if key != "type"}
        allowed = set(model.__table__.columns.keys())
        missing = required - data.keys()
        extra = data.keys() - allowed
        if missing or extra:
            raise ValueError(f"Record {index}: missing {sorted(missing)}, extra {sorted(extra)}")
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,59}", str(data["id"])):
            raise ValueError(f"Record {index}: id must be a lowercase slug")
        for field in ("source_url", "evidence_url", "website"):
            if field in data:
                validate_url(data[field])
        if kind in {"evidence", "use_case"} and data.get("company_id") and not session.get(Company, data["company_id"]):
            raise ValueError(f"Record {index}: company_id does not exist")
        if kind == "opportunity" and data.get("status", "hypothesis") != "hypothesis":
            raise ValueError(f"Record {index}: opportunities must remain labeled hypotheses")
        obj = session.get(model, data["id"])
        if obj:
            for key, value in data.items():
                if key != "id":
                    setattr(obj, key, value)
        else:
            session.add(model(**data))
        session.flush()
    session.commit()
    return len(records)


def main():
    parser = argparse.ArgumentParser(description="Import reviewed AItlas content from JSON")
    parser.add_argument("file", type=Path)
    args = parser.parse_args()
    records = json.loads(args.file.read_text())
    with SessionLocal() as session:
        print(f"Imported {import_records(session, records)} reviewed records")


if __name__ == "__main__":
    main()
