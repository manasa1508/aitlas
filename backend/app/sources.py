"""Operator-only source registry. No source management HTTP endpoints are exposed."""
import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import SessionLocal
from .models import Source

DEFAULTS = Path(__file__).resolve().parents[1] / "config" / "sources.json"
KINDS = {"rss", "arxiv", "hacker_news", "github_repos", "greenhouse_jobs", "hf_models"}
API_HOSTS = {"arxiv": "export.arxiv.org", "hacker_news": "hn.algolia.com", "github_repos": "api.github.com", "greenhouse_jobs": "boards-api.greenhouse.io", "hf_models": "huggingface.co"}


def validate_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("Source URL must be an HTTPS endpoint without embedded credentials")
    return url


def validate_source(kind: str, url: str, interval: int, options: dict) -> None:
    validate_url(url)
    if kind not in KINDS or not 5 <= interval <= 1440 or not isinstance(options, dict):
        raise ValueError("Invalid source kind, interval or options")
    if kind in API_HOSTS and urlparse(url).hostname != API_HOSTS[kind]:
        raise ValueError(f"{kind} source must use {API_HOSTS[kind]}")
    if kind == "greenhouse_jobs" and not re.fullmatch(r"/v1/boards/[a-zA-Z0-9_-]+/jobs", urlparse(url).path):
        raise ValueError("Greenhouse source must be a public board jobs endpoint")
    if kind == "hf_models" and urlparse(url).path != "/api/models":
        raise ValueError("Hugging Face source must use the public model listing endpoint")


def sync_defaults(session: Session) -> int:
    """Insert missing defaults; never overwrite an operator's changed settings."""
    count = 0
    for record in json.loads(DEFAULTS.read_text()):
        if session.get(Source, record["id"]):
            continue
        validate_source(record["kind"], record["url"], record["interval_minutes"], record.get("options", {}))
        session.add(Source(**record, enabled=True))
        count += 1
    session.commit()
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage AItlas sources")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list")
    commands.add_parser("sync-defaults")
    add = commands.add_parser("add-rss")
    add.add_argument("--id", required=True)
    add.add_argument("--name", required=True)
    add.add_argument("--url", required=True)
    add.add_argument("--interval", type=int, default=15)
    add.add_argument("--options", default="{}", help="JSON object of adapter options")
    general = commands.add_parser("add-source")
    general.add_argument("--id", required=True)
    general.add_argument("--name", required=True)
    general.add_argument("--url", required=True)
    general.add_argument("--kind", choices=sorted(KINDS), required=True)
    general.add_argument("--interval", type=int, default=30)
    general.add_argument("--options", default="{}")
    toggle = commands.add_parser("set-enabled")
    toggle.add_argument("id")
    toggle.add_argument("value", choices=["true", "false"])
    interval = commands.add_parser("set-interval")
    interval.add_argument("id")
    interval.add_argument("minutes", type=int)
    options_cmd = commands.add_parser("set-options")
    options_cmd.add_argument("id")
    options_cmd.add_argument("json_options")
    args = parser.parse_args()
    with SessionLocal() as session:
        if args.command == "sync-defaults":
            print(f"Added {sync_defaults(session)} default sources")
        elif args.command == "list":
            for row in session.scalars(select(Source).order_by(Source.name)).all():
                print(f"{row.id}\t{row.kind}\t{'enabled' if row.enabled else 'disabled'}\t{row.interval_minutes} min\t{row.url}")
        elif args.command in {"add-rss", "add-source"}:
            if session.get(Source, args.id):
                parser.error("source id already exists")
            try:
                options = json.loads(args.options)
                kind = args.kind if args.command == "add-source" else "rss"
                validate_source(kind, args.url, args.interval, options)
            except (ValueError, TypeError) as exc:
                parser.error(str(exc))
            session.add(Source(id=args.id, name=args.name, url=args.url, kind=kind, interval_minutes=args.interval, options=options))
            session.commit()
            print(f"Added {args.id}")
        else:
            row = session.get(Source, args.id)
            if not row:
                parser.error("source id not found")
            if args.command == "set-enabled":
                row.enabled = args.value == "true"
            elif args.command == "set-interval":
                if not 5 <= args.minutes <= 1440:
                    parser.error("interval must be 5–1440 minutes")
                row.interval_minutes = args.minutes
            elif args.command == "set-options":
                try:
                    options = json.loads(args.json_options)
                    validate_source(row.kind, row.url, row.interval_minutes, options)
                except (ValueError, TypeError) as exc:
                    parser.error(str(exc))
                row.options = options
            session.commit()
            print(f"Updated {row.id}")


if __name__ == "__main__":
    main()
