import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.engine import TrustEngine  # noqa: E402
from app.store import Store  # noqa: E402

DATA = ROOT / "data" / "acme"
NOW = datetime(2026, 11, 22, 10, 0, tzinfo=timezone.utc)


@pytest.fixture()
def store():
    return Store.from_dir(DATA)


@pytest.fixture()
def engine(store):
    return TrustEngine(store, lambda: NOW)
