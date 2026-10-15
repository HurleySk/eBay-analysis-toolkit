import pytest
from ebay_tracker.browser import BrowserFetcher, _should_block, parse_proxy_url


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


def test_parse_proxy_url_decodes_encoded_password():
    # Generated passwords can hold URL-special chars; the .env value encodes them
    result = parse_proxy_url("http://user-u-country-us:a%2Bb%3Dc%23d@gate.decodo.com:7000")
    assert result["password"] == "a+b=c#d"


def test_parse_proxy_url_no_auth():
    result = parse_proxy_url("http://proxy.example.com:8080")
    assert result["server"] == "http://proxy.example.com:8080"
    assert "username" not in result
    assert "password" not in result


def test_parse_proxy_url_none():
    result = parse_proxy_url(None)
    assert result is None


def test_block_resources_skips_images_media_fonts():
    assert _should_block("image")
    assert _should_block("media")
    assert _should_block("font")
    assert not _should_block("document")
    assert not _should_block("script")
    assert not _should_block("xhr")


def test_browser_fetcher_block_resources_off_by_default():
    assert BrowserFetcher(proxy_url=None)._block_resources is False
    assert BrowserFetcher(proxy_url=None, block_resources=True)._block_resources is True


def test_browser_fetcher_not_running_initially():
    fetcher = BrowserFetcher(proxy_url=None)
    assert fetcher.is_running is False


@pytest.mark.browser
def test_browser_fetcher_start_stop():
    fetcher = BrowserFetcher(proxy_url=None)
    fetcher.start(warmup_url=None)
    assert fetcher.is_running is True
    fetcher.stop()
    assert fetcher.is_running is False


@pytest.mark.browser
def test_browser_fetcher_fetch_returns_html():
    fetcher = BrowserFetcher(proxy_url=None)
    fetcher.start(warmup_url=None)
    try:
        html = fetcher.fetch("https://example.com")
        assert "<html" in html.lower() or "<!doctype" in html.lower()
        assert len(html) > 100
    finally:
        fetcher.stop()


@pytest.mark.browser
def test_browser_fetcher_auto_starts_on_fetch():
    fetcher = BrowserFetcher(proxy_url=None)
    assert fetcher.is_running is False
    try:
        html = fetcher.fetch("https://example.com")
        assert fetcher.is_running is True
        assert len(html) > 100
    finally:
        fetcher.stop()


def test_browser_fetcher_stop_when_not_running():
    fetcher = BrowserFetcher(proxy_url=None)
    fetcher.stop()
    assert fetcher.is_running is False
