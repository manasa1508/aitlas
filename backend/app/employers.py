"""Persistent employer discovery. No unverified job feeds are auto-enabled."""
import argparse
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlparse

from sqlalchemy import select

from .db import SessionLocal, utcnow
from .jobs import JOB_SOURCE_KINDS, job_board_url
from .models import Employer, EmployerCatalog, Source

CONFIG = Path(__file__).resolve().parents[1] / "config"


def name_key(name):
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return " ".join(re.findall(r"[a-z0-9]+", text))


def employer_index(session):
    rows = session.scalars(select(Employer)).all()
    index = {}
    for row in rows:
        for value in [row.name, *(row.profile or {}).get("aliases", [])]:
            key = name_key(value)
            if key in index and index[key].id != row.id:
                raise ValueError(f"Ambiguous employer alias: {value}")
            index[key] = row
    return rows, index


def ensure_employer(session, index, name, *, profile=None, careers_url=None, manual=False):
    key = name_key(name)
    if not key or len(name) > 200 or len(key) > 220:
        raise ValueError("Invalid employer name")
    row = index.get(key)
    if row:
        return row, False
    identifier = key.replace(" ", "-")[:72] + "-" + sha256(key.encode()).hexdigest()[:12]
    row = Employer(id=identifier, name=name, name_key=key, profile=profile or {}, careers_url=careers_url, manual=manual, references=[], active=True)
    session.add(row)
    for value in [name, *(profile or {}).get("aliases", [])]:
        alias = name_key(value)
        if alias in index and index[alias] is not row:
            raise ValueError(f"Ambiguous employer alias: {value}")
        index[alias] = row
    return row, True


def sync_employer_defaults(session):
    """One-time starter import; never overwrite an existing employer or review."""
    data = json.loads((CONFIG / "intelligence.json").read_text())
    aliases_path = CONFIG / "employer_aliases.json"
    aliases = json.loads(aliases_path.read_text()) if aliases_path.exists() else {}
    sources = json.loads((CONFIG / "sources.json").read_text())
    entries = {entry["name"]: entry for entry in data["career_links"]}
    for source in sources:
        if source["kind"] in JOB_SOURCE_KINDS:
            name = source.get("options", {}).get("company", source["name"])
            entries[name] = {"name": name, "url": job_board_url(Source(**source))}
    _, index = employer_index(session)
    for entry in data.get("employer_discovery_sources", []):
        if not session.get(EmployerCatalog, entry["id"]):
            session.add(EmployerCatalog(id=entry["id"], title=entry["title"], url=entry["url"], status=entry["status"], checked_at=utcnow()))
    for name, entry in entries.items():
        profile = {"category": entry.get("category", "Product and technology"), **data.get("employer_profiles", {}).get(name, {})}
        profile["aliases"] = aliases.get(name, [])
        row, created = ensure_employer(session, index, name, profile=profile, careers_url=entry["url"], manual=True)
        if created:
            row.references = [{"id": key, "present": True, "misses": 0, "last_seen_at": utcnow().isoformat()} for key in profile.get("discovery_source_ids", [])]
    session.flush()
    register_configured_sources(session, index=index)
    session.commit()


def register_configured_sources(session, *, index=None):
    if index is None:
        _, index = employer_index(session)
    for source in session.scalars(select(Source)).all():
        if source.kind in JOB_SOURCE_KINDS:
            name = str((source.options or {}).get("company") or source.name)
            row, _ = ensure_employer(session, index, name, careers_url=job_board_url(source), manual=True)
            row.active = True
            row.manual = True
            if row.careers_url is None:
                row.careers_url = job_board_url(source)
        elif source.kind == "employer_catalog":
            identifier = (source.options or {}).get("reference_id", source.id)
            provider = session.get(EmployerCatalog, identifier)
            if not provider:
                session.add(EmployerCatalog(id=identifier, title=(source.options or {}).get("title", source.name), url=source.url, status="unavailable", source_id=source.id))
            elif provider.source_id is None:
                provider.source_id = source.id
    session.flush()


class CompanyTable(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.tables, self.rows, self.row, self.cell = [], [], None, None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.depth += 1
            if self.depth == 1:
                self.rows = []
        elif self.depth == 1 and tag == "tr":
            self.row = []
        elif self.depth == 1 and tag in {"td", "th"} and self.row is not None:
            self.cell = []

    def handle_data(self, value):
        if self.cell is not None:
            self.cell.append(value)

    def handle_endtag(self, tag):
        if tag in {"td", "th"} and self.cell is not None and self.row is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.depth == 1 and self.row is not None:
            self.rows.append(self.row)
            self.row = None
        elif tag == "table" and self.depth:
            if self.depth == 1:
                self.tables.append(self.rows)
                self.rows = []
            self.depth -= 1


def parse_us500(body, *, min_rows=400, max_rows=750, previous_size=0):
    parser = CompanyTable()
    parser.feed(body)
    tables = [rows for rows in parser.tables if rows and len(rows[0]) >= 2 and [cell.lower() for cell in rows[0][:2]] == ["rank", "company"]]
    if len(tables) != 1:
        raise ValueError("US500 company table missing or ambiguous; previous catalog retained")
    records, seen = [], set()
    for position, cells in enumerate(tables[0][1:], 1):
        if len(cells) < 2 or cells[0] != str(position):
            raise ValueError("Incomplete or changed US500 table; previous catalog retained")
        name = cells[1]
        key = name_key(name)
        if not 2 <= len(name) <= 200 or not key or key in seen:
            raise ValueError("Invalid or duplicate US500 company")
        seen.add(key)
        records.append({"name": name})
    if not min_rows <= len(records) <= max_rows or (previous_size and len(records) < previous_size * .8):
        raise ValueError("Unexpected US500 catalog size; previous catalog retained")
    return records


def sync_catalog_snapshot(session, source, records, *, observed_at=None):
    """No job availability changes. Two complete misses withdraw only a citation."""
    names, keys = [], set()
    for record in records:
        name = record.get("name") if isinstance(record, dict) else None
        if not isinstance(name, str) or not 2 <= len(name.strip()) <= 200 or not name_key(name) or name_key(name) in keys:
            raise ValueError("Malformed employer snapshot; previous catalog retained")
        names.append(name.strip()); keys.add(name_key(name))
    if not 1 <= len(names) <= 5000:
        raise ValueError("Invalid employer snapshot size")
    register_configured_sources(session)
    rows, index = employer_index(session)
    identifier = (source.options or {}).get("reference_id", source.id)
    provider = session.get(EmployerCatalog, identifier)
    now = observed_at or utcnow()
    previous = provider.checked_at
    if previous and previous.tzinfo is None:
        previous = previous.replace(tzinfo=timezone.utc)
    if previous and now < previous:
        raise ValueError("Observation is older than the current employer catalog")
    seen, added = set(), 0
    for name in names:
        row, created = ensure_employer(session, index, name, profile={"category": "Company discovery", "aliases": []})
        added += int(created)
        refs = [entry for entry in row.references if entry["id"] != identifier]
        refs.append({"id": identifier, "present": True, "misses": 0, "last_seen_at": now.isoformat(), "listed_name": name})
        row.references = refs
        row.active = True
        row.updated_at = now
        seen.add(row.id)
    for row in rows:
        if row.id in seen:
            continue
        refs = []
        for entry in row.references:
            if entry["id"] == identifier:
                entry = {**entry, "misses": entry.get("misses", 0) + 1}
                entry["present"] = entry["misses"] < 2
            refs.append(entry)
        row.references = refs
        if not row.manual and not row.careers_url and refs and not any(entry.get("present", True) for entry in refs):
            row.active = False
    provider.status, provider.checked_at = "reviewed", now
    source.options = {**(source.options or {}), "snapshot_size": len(records)}
    session.flush()
    return added


def main():
    parser = argparse.ArgumentParser(description="Manage the persistent employer catalog")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("sync-defaults")
    importer = sub.add_parser("import-observed", help="Import a reviewed observation without changing network health")
    importer.add_argument("path")
    importer.add_argument("--source", required=True)
    editor = sub.add_parser("set-careers", help="Attach a reviewed official careers URL; does not enable a job feed")
    editor.add_argument("employer_id")
    editor.add_argument("url")
    args = parser.parse_args()
    with SessionLocal() as session:
        if args.command == "sync-defaults":
            sync_employer_defaults(session)
        elif args.command == "set-careers":
            parsed = urlparse(args.url)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                parser.error("Careers URL must be a reviewed HTTPS address without embedded credentials")
            row = session.get(Employer, args.employer_id)
            if not row:
                parser.error("Employer not found")
            row.careers_url, row.manual, row.updated_at = args.url, True, utcnow()
            session.commit()
        else:
            data = json.loads(Path(args.path).read_text())
            source = session.get(Source, args.source)
            if not source or source.kind != "employer_catalog" or data.get("url") != source.url:
                parser.error("Observation must match an existing employer catalog source")
            observed = datetime.fromisoformat(data["observed_at"])
            if observed.tzinfo is None or observed > utcnow():
                parser.error("Observation needs a past timestamp with timezone")
            if observed < utcnow() - timedelta(days=365):
                parser.error("Observation is too old")
            count = sync_catalog_snapshot(session, source, data["companies"], observed_at=observed)
            source.options = {**source.options, "snapshot_origin": "observed_import"}
            session.commit()
            print(f"Imported {len(data['companies'])} observed companies; {count} new employers")


if __name__ == "__main__":
    main()
