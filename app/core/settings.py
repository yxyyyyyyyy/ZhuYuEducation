from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT_DIR / ".env"


def load_environment() -> Path:
    load_dotenv(ENV_FILE, override=False)
    return ENV_FILE
