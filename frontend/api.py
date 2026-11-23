"""Tiny client for the FastAPI backend. Returns (ok, data_or_error_message)."""
import os

import requests

BASE = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")


def call(method: str, path: str, payload=None, params=None, timeout=90):
    try:
        r = requests.request(method, BASE + path, json=payload, params=params, timeout=timeout)
    except requests.exceptions.ConnectionError:
        return False, "Backend is not reachable. Start it with run_windows.bat (or: python -m uvicorn backend.main:app)."
    except requests.exceptions.Timeout:
        return False, "The backend took too long to respond."
    try:
        body = r.json()
    except ValueError:
        return False, f"Unexpected response ({r.status_code})."
    if r.ok:
        return True, body
    detail = body.get("detail", body) if isinstance(body, dict) else body
    if isinstance(detail, list):  # pydantic validation errors
        detail = "; ".join(f"{'.'.join(map(str, d.get('loc', [])[1:]))}: {d.get('msg')}" for d in detail)
    return False, str(detail)
