import pytest
from ebay_tracker.browser import BrowserFetcher, parse_proxy_url


def test_parse_proxy_url_full():
    result = parse_proxy_url("http://user-myuser-country-us:mypass@gate.decodo.com:7000")
    assert result["server"] == "http://gate.decodo.com:7000"
    assert result["username"] == "user-myuser-country-us"
    assert result["password"] == "mypass"


def test_parse_proxy_url_simple():
    result = parse_proxy_url("http://admin:secret@proxy.example.com:8080")
    assert result["server"] == "http://proxy.example.com:8080"
    assert result["username"] == "admin"
    assert result["password"] == "secret"


def test_parse_proxy_url_no_auth():
    result = parse_proxy_url("http://proxy.example.com:8080")
    assert result["server"] == "http://proxy.example.com:8080"
    assert "username" not in result
    assert "password" not in result


def test_parse_proxy_url_none():
    result = parse_proxy_url(None)
    assert result is None


def test_browser_fetcher_not_running_initially():
    fetcher = BrowserFetcher(proxy_url=None)
    assert fetcher.is_running is False


def test_browser_fetcher_start_stop():
    fetcher = BrowserFetcher(proxy_url=None)
    fetcher.start()
    assert fetcher.is_running is True
    fetcher.stop()
    assert fetcher.is_running is False


def test_browser_fetcher_fetch_returns_html():
    fetcher = BrowserFetcher(proxy_url=None)
    fetcher.start()
    try:
        html = fetcher.fetch("https://example.com")
        assert "<html" in html.lower() or "<!doctype" in html.lower()
        assert len(html) > 100
    finally:
        fetcher.stop()


def test_browser_fetcher_auto_starts_on_fetch():
    fetcher = BrowserFetcher(proxy_url=None)
    assert fetcher.is_running is False
    html = fetcher.fetch("https://example.com")
    assert fetcher.is_running is True
    assert len(html) > 100
    fetcher.stop()


def test_browser_fetcher_stop_when_not_running():
    fetcher = BrowserFetcher(proxy_url=None)
    fetcher.stop()
    assert fetcher.is_running is False
