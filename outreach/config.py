"""Runtime configuration.

Everything tunable lives in .env or config/icp.yaml. The one thing that is
deliberately NOT configurable is the email recipient: the case requires the
`to:` address to be hardcoded to the student's own inbox.
"""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# [CASE REQUIREMENT] Step 7 - hardcode `to:` as your own email address.
# Not read from env on purpose, so no config change can redirect a send.
HARDCODED_RECIPIENT = "vyom_bhatnagar@pg27.mesaschool.co"

PROMPT_VERSION = "v1"  # bumped whenever a prompt changes; recorded in every trace


def _bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str
    model: str
    extract_model: str
    hunter_api_key: str
    gmail_mode: str
    gmail_sender: str
    gmail_app_password: str
    agent_max_rounds: int
    review_before_send: bool
    jina_fallback: bool
    scrape_delay: float
    database_url: str
    icp_path: Path
    runs_dir: Path
    secrets_dir: Path
    manual_pocs_path: Path

    @property
    def recipient(self) -> str:
        return HARDCODED_RECIPIENT


def load_settings() -> Settings:
    return Settings(
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        model=os.getenv("OUTREACH_MODEL", "claude-opus-5-5"),
        # L4 slide 15: cleaned text into a cheap model gives the same extraction for a fraction of the cost
        extract_model=os.getenv("EXTRACT_MODEL", "claude-haiku-5-5"),
        hunter_api_key=os.getenv("HUNTER_API_KEY", ""),
        gmail_mode=os.getenv("GMAIL_MODE", "oauth").strip().lower(),
        gmail_sender=os.getenv("GMAIL_SENDER", ""),
        gmail_app_password=os.getenv("GMAIL_APP_PASSWORD", ""),
        agent_max_rounds=int(os.getenv("AGENT_MAX_ROUNDS", "4")),
        review_before_send=_bool(os.getenv("REVIEW_BEFORE_SEND", "false")),
        jina_fallback=_bool(os.getenv("JINA_FALLBACK", "true")),
        scrape_delay=float(os.getenv("SCRAPE_DELAY_SECONDS", "1.0")),
        database_url=os.getenv("DATABASE_URL", "") or os.getenv("POSTGRES_URL", ""),
        icp_path=ROOT / "config" / "icp.yaml",
        runs_dir=Path(os.getenv("RUNS_DIR", str(ROOT / "runs"))),
        secrets_dir=ROOT / "secrets",
        manual_pocs_path=ROOT / "data" / "manual_pocs.json",
    )
