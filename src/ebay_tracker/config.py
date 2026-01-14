from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    proxy_url: str | None
    db_path: Path


def get_config() -> Config:
    return Config(
        proxy_url=os.environ.get("DECODO_PROXY_URL"),
        db_path=Path(os.environ.get("EBAY_TRACKER_DB_PATH", "data/ebay_tracker.db")),
    )
