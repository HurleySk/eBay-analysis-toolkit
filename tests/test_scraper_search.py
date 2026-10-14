from urllib.parse import parse_qs, urlparse

import pytest

from ebay_tracker.scraper import build_search_url


def _params(url):
    return {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}


def test_build_search_url_defaults_to_sold():
    p = _params(build_search_url("alden indy"))
    assert p["LH_Sold"] == "1" and p["LH_Complete"] == "1"
    assert p["_ipg"] == "240"
    assert "LH_BIN" not in p and "_sop" not in p


def test_build_search_url_active_bin():
    p = _params(build_search_url("alden indy", {"condition": "pre-owned"}, sold=False, buying_format="bin"))
    assert "LH_Sold" not in p and "LH_Complete" not in p
    assert p["LH_BIN"] == "1"
    assert p["LH_ItemCondition"] == "3000"


def test_build_search_url_sort_and_auction():
    p = _params(build_search_url("x", sold=False, buying_format="auction", sort="ending_soonest"))
    assert p["LH_Auction"] == "1"
    assert p["_sop"] == "1"
    assert _params(build_search_url("x", sold=False, sort="newly_listed"))["_sop"] == "10"
    assert _params(build_search_url("x", sold=False, sort="price_low"))["_sop"] == "15"


def test_build_search_url_rejects_unknown_options():
    with pytest.raises(ValueError):
        build_search_url("x", buying_format="best_offer")
    with pytest.raises(ValueError):
        build_search_url("x", sort="random")
