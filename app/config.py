"""Central configuration, loaded from environment variables / .env file."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _float(name: str, default: float) -> float:
    raw = _env(name)
    return float(raw) if raw else default


def _int(name: str, default: int) -> int:
    raw = _env(name)
    return int(raw) if raw else default


def _optional_float(name: str) -> float | None:
    raw = _env(name)
    return float(raw) if raw else None


@dataclass
class Settings:
    llm_provider: str = field(default_factory=lambda: _env("LLM_PROVIDER", "anthropic").lower())
    anthropic_api_key: str = field(default_factory=lambda: _env("ANTHROPIC_API_KEY"))
    anthropic_model: str = field(default_factory=lambda: _env("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"))
    openai_api_key: str = field(default_factory=lambda: _env("OPENAI_API_KEY"))
    openai_model: str = field(default_factory=lambda: _env("OPENAI_MODEL", "gpt-4.1-mini"))
    temperature: float | None = field(default_factory=lambda: _optional_float("LLM_TEMPERATURE"))
    anthropic_price_input: float = field(default_factory=lambda: _float("ANTHROPIC_PRICE_INPUT_PER_MTOK", 1.0))
    anthropic_price_output: float = field(default_factory=lambda: _float("ANTHROPIC_PRICE_OUTPUT_PER_MTOK", 5.0))
    openai_price_input: float = field(default_factory=lambda: _float("OPENAI_PRICE_INPUT_PER_MTOK", 0.40))
    openai_price_output: float = field(default_factory=lambda: _float("OPENAI_PRICE_OUTPUT_PER_MTOK", 1.60))

    max_pages: int = field(default_factory=lambda: _int("MAX_PAGES", 3))
    render_scale: float = field(default_factory=lambda: _float("RENDER_SCALE", 1.6))
    max_tax_rate: float = field(default_factory=lambda: _float("MAX_TAX_RATE", 0.30))

    host: str = field(default_factory=lambda: _env("HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: _int("PORT", 8200))
    db_path: Path = field(default_factory=lambda: ROOT_DIR / _env("DB_PATH", "data/folio.db"))
    storage_dir: Path = field(default_factory=lambda: ROOT_DIR / "data" / "store")
    outputs_dir: Path = field(default_factory=lambda: ROOT_DIR / "outputs")
    samples_dir: Path = field(default_factory=lambda: ROOT_DIR / "data" / "samples")

    vendors_path: Path = field(default_factory=lambda: ROOT_DIR / _env("VENDORS_FILE", "config/vendors.json"))

    def vendors(self) -> list[dict]:
        """The vendor master; empty list (checks skipped) if the file doesn't exist."""
        import json
        return json.loads(self.vendors_path.read_text(encoding="utf-8")) if self.vendors_path.exists() else []

    @property
    def eval_results_path(self) -> Path:
        return self.outputs_dir / "eval_results.json"

    @property
    def model_name(self) -> str:
        return self.anthropic_model if self.llm_provider.startswith(("anthropic", "claude")) else self.openai_model


def get_settings() -> Settings:
    return Settings()
