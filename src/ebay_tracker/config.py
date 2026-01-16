import json
from dataclasses import dataclass, field
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


@dataclass
class UserPreferences:
    gender_preference: str | None = None
    favorite_categories: list[int] = field(default_factory=list)


def get_prefs_path() -> Path:
    return Path.home() / ".config" / "ebay-tracker" / "config.json"


def get_user_prefs() -> UserPreferences:
    path = get_prefs_path()
    if path.exists():
        data = json.loads(path.read_text())
        return UserPreferences(
            gender_preference=data.get("gender_preference"),
            favorite_categories=data.get("favorite_categories", []),
        )
    return UserPreferences()


def save_user_prefs(prefs: UserPreferences) -> None:
    path = get_prefs_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "gender_preference": prefs.gender_preference,
        "favorite_categories": prefs.favorite_categories,
    }, indent=2))
