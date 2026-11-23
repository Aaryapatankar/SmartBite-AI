"""Central configuration. Secrets are read from environment variables (.env), never hardcoded."""
import os
from pathlib import Path

try:  # python-dotenv is optional; .env is loaded if available
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
KNOWLEDGE_DIR = DATA_DIR / "knowledge"
STORAGE_DIR = BASE_DIR / "storage"
CHROMA_DIR = STORAGE_DIR / "chroma"


def env(name: str, default: str = "") -> str:
    """Read an environment variable at call time (so tests can change it)."""
    return os.getenv(name, default).strip()


def db_path() -> Path:
    return Path(env("SMARTBITE_DB", str(STORAGE_DIR / "smartbite.db")))
