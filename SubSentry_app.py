"""Compatibility shim — main entrypoint moved to `legacy/SubSentry_app.py`.

If you need to run the application directly for development, prefer:

    uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 4399

This file is kept to avoid breaking scripts that import it.
"""

from legacy import SubSentry_app  # noqa: F401
