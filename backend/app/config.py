"""Runtime configuration, read from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "acme"


def _parse_now(raw: str | None) -> datetime | None:
    if not raw:
        return None
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("DT_DATA_DIR", str(DEFAULT_DATA_DIR))))
    # Fixed clock for reproducible demos and tests. Unset = real time.
    demo_now: datetime | None = field(default_factory=lambda: _parse_now(os.getenv("DT_DEMO_NOW", "2026-11-22T10:00:00Z")))
    anthropic_api_key: str | None = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY"))
    claude_model: str = field(default_factory=lambda: os.getenv("DT_CLAUDE_MODEL", "claude-sonnet-5-5"))
    claude_fast_model: str = field(default_factory=lambda: os.getenv("DT_CLAUDE_FAST_MODEL", "claude-haiku-5-5"))
    neo4j_uri: str | None = field(default_factory=lambda: os.getenv("NEO4J_URI"))
    neo4j_user: str = field(default_factory=lambda: os.getenv("NEO4J_USER", "neo4j"))
    neo4j_password: str = field(default_factory=lambda: os.getenv("NEO4J_PASSWORD", "decisiontrust"))
    workspace_id: str = field(default_factory=lambda: os.getenv("DT_WORKSPACE", "acme"))
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(os.getenv("DT_CORS_ORIGINS", "http://localhost:3000").split(","))
    )

    def now(self) -> datetime:
        return self.demo_now or datetime.now(timezone.utc)


settings = Settings()
