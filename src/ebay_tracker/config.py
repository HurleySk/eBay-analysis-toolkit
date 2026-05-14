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
class FeeConfig:
    final_value_pct: float = 13.25
    payment_processing_pct: float = 2.35
    payment_processing_flat: float = 0.30
    shipping_cost: float = 0.00
    sales_tax_rate: float = 0.00
    state: str | None = None


@dataclass
class ThresholdConfig:
    min_profit_pct: float = 20.0
    min_profit_dollar: float = 10.0
    mode: str = "and"

    def check(self, profit_pct: float, profit_dollar: float) -> bool:
        pct_pass = profit_pct >= self.min_profit_pct
        dollar_pass = profit_dollar >= self.min_profit_dollar
        if self.mode == "or":
            return pct_pass or dollar_pass
        return pct_pass and dollar_pass

    def explain(self, profit_pct: float, profit_dollar: float) -> str:
        pct_pass = profit_pct >= self.min_profit_pct
        dollar_pass = profit_dollar >= self.min_profit_dollar
        passes = self.check(profit_pct, profit_dollar)
        op = self.mode.upper()
        verdict = "PASS" if passes else "FAIL"
        return (
            f"{profit_pct:.1f}% >= {self.min_profit_pct}% {'OK' if pct_pass else 'NO'} "
            f"{op} ${profit_dollar:.2f} >= ${self.min_profit_dollar:.2f} {'OK' if dollar_pass else 'NO'}: "
            f"{verdict}"
        )


@dataclass
class UserPreferences:
    gender_preference: str | None = None
    favorite_categories: list[int] = field(default_factory=list)
    fees: FeeConfig = field(default_factory=FeeConfig)
    thresholds: ThresholdConfig = field(default_factory=ThresholdConfig)


def get_prefs_path() -> Path:
    return Path.home() / ".config" / "ebay-tracker" / "config.json"


def get_user_prefs() -> UserPreferences:
    path = get_prefs_path()
    if path.exists():
        data = json.loads(path.read_text())
        fees_data = data.get("fees", {})
        thresholds_data = data.get("thresholds", {})
        return UserPreferences(
            gender_preference=data.get("gender_preference"),
            favorite_categories=data.get("favorite_categories", []),
            fees=FeeConfig(
                final_value_pct=fees_data.get("final_value_pct", 13.25),
                payment_processing_pct=fees_data.get("payment_processing_pct", 2.35),
                payment_processing_flat=fees_data.get("payment_processing_flat", 0.30),
                shipping_cost=fees_data.get("shipping_cost", 0.00),
                sales_tax_rate=fees_data.get("sales_tax_rate", 0.00),
                state=fees_data.get("state"),
            ),
            thresholds=ThresholdConfig(
                min_profit_pct=thresholds_data.get("min_profit_pct", 20.0),
                min_profit_dollar=thresholds_data.get("min_profit_dollar", 10.0),
                mode=thresholds_data.get("mode", "and"),
            ),
        )
    return UserPreferences()


def save_user_prefs(prefs: UserPreferences) -> None:
    path = get_prefs_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "gender_preference": prefs.gender_preference,
        "favorite_categories": prefs.favorite_categories,
        "fees": {
            "final_value_pct": prefs.fees.final_value_pct,
            "payment_processing_pct": prefs.fees.payment_processing_pct,
            "payment_processing_flat": prefs.fees.payment_processing_flat,
            "shipping_cost": prefs.fees.shipping_cost,
            "sales_tax_rate": prefs.fees.sales_tax_rate,
            "state": prefs.fees.state,
        },
        "thresholds": {
            "min_profit_pct": prefs.thresholds.min_profit_pct,
            "min_profit_dollar": prefs.thresholds.min_profit_dollar,
            "mode": prefs.thresholds.mode,
        },
    }, indent=2))
