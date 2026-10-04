"""Run the recommendation web search + seed recommended first cars.

Run:  python scripts/run_recommendations.py

Uses Tavily if TAVILY_API_KEY is set (in .env), otherwise the bundled
authoritative knowledge base. Always seeds the curated first-car models.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pplate.db import SessionLocal, init_db  # noqa: E402
from pplate.services.recommendation_search import run_recommendation_search  # noqa: E402


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        result = run_recommendation_search(db, seed_recommended_cars=True)
        print(json.dumps(result, indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()
