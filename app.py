"""Top-level ASGI entry point.

Run with:  uvicorn app:app --reload
"""

from pplate.main import app

__all__ = ["app"]
