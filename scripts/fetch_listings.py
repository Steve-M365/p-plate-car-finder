"""Fetch live (or mock/CSV) listings and tag P-plate compliance.

Run:  python scripts/fetch_listings.py [--provider mock|csv|carsales|auto] [--query "Toyota Corolla"] [--limit 25]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pplate.db import SessionLocal, init_db  # noqa: E402
from pplate.services.listing_fetch import fetch_listings  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch used-car listings into the local DB.")
    parser.add_argument("--provider", default=None, help="mock | csv | feed | ebay | carsales | auto")
    parser.add_argument("--query", default=None, help="Optional model search, e.g. 'Toyota Corolla'")
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        result = fetch_listings(db, provider=args.provider, query=args.query, limit=args.limit)
        print(json.dumps(result, indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()
