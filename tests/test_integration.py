"""Integration tests for end-to-end workflows."""

import pytest
from typer.testing import CliRunner
from pathlib import Path
import tempfile


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def temp_env(monkeypatch):
    """Set up temporary environment for integration tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        monkeypatch.setenv("EBAY_TRACKER_DB_PATH", str(db_path))
        # Don't set proxy - we'll mock the scraper
        monkeypatch.delenv("DECODO_PROXY_URL", raising=False)
        yield tmpdir


def test_full_workflow_with_mock_data(runner, temp_env, monkeypatch):
    """Test complete workflow: add -> (mock) fetch -> analyze."""
    from ebay_tracker.cli import app

    # Mock the fetch_page function to return test data
    def mock_fetch_page(url, proxy_url=None):
        return """
        <ul class="srp-results">
          <li class="s-item">
            <a class="s-item__link" href="https://www.ebay.com/itm/111111111">
              <div class="s-item__title">Test Item 1</div>
            </a>
            <span class="s-item__price">$30.00</span>
            <span class="s-item__shipping">Free shipping</span>
            <span class="SECONDARY_INFO">Pre-owned</span>
            <span class="POSITIVE">Sold  Jan 1, 2025</span>
          </li>
          <li class="s-item">
            <a class="s-item__link" href="https://www.ebay.com/itm/222222222">
              <div class="s-item__title">Test Item 2</div>
            </a>
            <span class="s-item__price">$50.00</span>
            <span class="s-item__shipping">+$5.00 shipping</span>
            <span class="SECONDARY_INFO">Pre-owned</span>
            <span class="POSITIVE">Sold  Jan 10, 2025</span>
          </li>
          <li class="s-item">
            <a class="s-item__link" href="https://www.ebay.com/itm/333333333">
              <div class="s-item__title">Test Item 3</div>
            </a>
            <span class="s-item__price">$40.00</span>
            <span class="s-item__shipping">Free shipping</span>
            <span class="SECONDARY_INFO">New</span>
            <span class="POSITIVE">Sold  Jan 20, 2025</span>
          </li>
        </ul>
        """

    # Patch where the functions are used, not where they're defined
    from ebay_tracker import cli
    monkeypatch.setattr(cli, "fetch_page", mock_fetch_page)

    # 1. Add a search
    result = runner.invoke(app, ["add", "Test Search"])
    assert result.exit_code == 0
    assert "Added" in result.stdout or "added" in result.stdout.lower()

    # 2. List searches
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "Test Search" in result.stdout

    # 3. Fetch listings
    result = runner.invoke(app, ["fetch", "Test Search"])
    assert result.exit_code == 0
    assert "3" in result.stdout  # Found 3 listings

    # 4. Analyze
    result = runner.invoke(app, ["analyze", "Test Search"])
    assert result.exit_code == 0
    assert "3 sales" in result.stdout.lower() or "(3" in result.stdout
    assert "$40" in result.stdout  # Median price

    # 5. Analyze with target price
    result = runner.invoke(app, ["analyze", "Test Search", "--target-price", "35"])
    assert result.exit_code == 0

    # 6. History
    result = runner.invoke(app, ["history", "Test Search"])
    assert result.exit_code == 0
    assert "Test Item" in result.stdout

    # 7. Export
    result = runner.invoke(app, ["export", "Test Search"])
    assert result.exit_code == 0
    assert "111111111" in result.stdout  # Item ID in CSV

    # 8. Remove
    result = runner.invoke(app, ["remove", "Test Search"])
    assert result.exit_code == 0
    assert "Removed" in result.stdout or "removed" in result.stdout.lower()

    # 9. Verify removed
    result = runner.invoke(app, ["list"])
    assert "Test Search" not in result.stdout or "No searches" in result.stdout
