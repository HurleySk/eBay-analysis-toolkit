import os
from pathlib import Path


def test_get_config_returns_defaults_when_no_env():
    # Clear any existing env vars
    os.environ.pop("DECODO_PROXY_URL", None)
    os.environ.pop("EBAY_TRACKER_DB_PATH", None)

    from ebay_tracker.config import get_config

    config = get_config()

    assert config.proxy_url is None
    assert config.db_path == Path("data/ebay_tracker.db")


def test_get_config_reads_from_env():
    os.environ["DECODO_PROXY_URL"] = "http://test:pass@proxy.example.com:8080"
    os.environ["EBAY_TRACKER_DB_PATH"] = "/custom/path/test.db"

    from ebay_tracker import config
    # Force reload
    import importlib
    importlib.reload(config)

    cfg = config.get_config()

    assert cfg.proxy_url == "http://test:pass@proxy.example.com:8080"
    assert cfg.db_path == Path("/custom/path/test.db")

    # Cleanup
    os.environ.pop("DECODO_PROXY_URL", None)
    os.environ.pop("EBAY_TRACKER_DB_PATH", None)
