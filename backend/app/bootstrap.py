"""Apply versioned schema and seed reviewed starter records."""
from pathlib import Path

from alembic import command
from alembic.config import Config

from .db import SessionLocal
from .seed import seed
from .sources import sync_defaults


def main() -> None:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    with SessionLocal() as session:
        seed(session)
        sync_defaults(session)
    print("AItlas schema and starter corpus ready")


if __name__ == "__main__":
    main()
