"""Dedicated ingestion worker; never run as part of API request processing."""
import argparse
import logging
import time

from sqlalchemy import text

from .db import SessionLocal, engine, settings
from .ingest import run_ingestion


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run one ingestion cycle and exit")
    parser.add_argument("--force", action="store_true", help="Ignore source schedules for this cycle")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    while True:
        if engine.dialect.name == "postgresql":
            # A session-level advisory lock prevents duplicate jobs when workers restart or scale out.
            with engine.connect() as lock_connection:
                acquired = lock_connection.scalar(text("SELECT pg_try_advisory_lock(48290517)"))
                if acquired:
                    try:
                        with SessionLocal() as session:
                            run_ingestion(session, force=args.force)
                    finally:
                        lock_connection.execute(text("SELECT pg_advisory_unlock(48290517)"))
                else:
                    logging.info("Another worker is running ingestion; skipping this cycle")
        else:
            with SessionLocal() as session:
                run_ingestion(session, force=args.force)
        if args.once:
            break
        time.sleep(max(15, settings.worker_tick_seconds))


if __name__ == "__main__":
    main()
