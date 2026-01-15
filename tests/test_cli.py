import pytest
from typer.testing import CliRunner
from pathlib import Path
import tempfile


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def temp_db(monkeypatch):
    """Use a temporary database for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        monkeypatch.setenv("EBAY_TRACKER_DB_PATH", str(db_path))
        yield db_path


def test_cli_help(runner):
    from ebay_tracker.cli import app

    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "ebay-tracker" in result.stdout.lower() or "usage" in result.stdout.lower()


def test_cli_add_search(runner, temp_db):
    from ebay_tracker.cli import app

    result = runner.invoke(app, ["add", "Levi's 501 32x30"])

    assert result.exit_code == 0
    assert "added" in result.stdout.lower() or "Levi" in result.stdout


def test_cli_add_search_with_options(runner, temp_db):
    from ebay_tracker.cli import app

    result = runner.invoke(app, [
        "add", "Levi's 501 32x30",
        "--condition", "Pre-owned",
        "--max-price", "100"
    ])

    assert result.exit_code == 0


def test_cli_list_searches_empty(runner, temp_db):
    from ebay_tracker.cli import app

    result = runner.invoke(app, ["list"])

    assert result.exit_code == 0
    assert "no searches" in result.stdout.lower() or result.stdout.strip() == ""


def test_cli_list_searches_with_items(runner, temp_db):
    from ebay_tracker.cli import app

    # Add a search first
    runner.invoke(app, ["add", "Levi's 501 32x30"])

    result = runner.invoke(app, ["list"])

    assert result.exit_code == 0
    assert "Levi" in result.stdout


def test_cli_remove_search(runner, temp_db):
    from ebay_tracker.cli import app

    # Add then remove
    runner.invoke(app, ["add", "Levi's 501 32x30"])
    result = runner.invoke(app, ["remove", "Levi's 501 32x30"])

    assert result.exit_code == 0
    assert "removed" in result.stdout.lower() or "deleted" in result.stdout.lower()


def test_cli_remove_nonexistent(runner, temp_db):
    from ebay_tracker.cli import app

    result = runner.invoke(app, ["remove", "Nonexistent Search"])

    assert result.exit_code == 1 or "not found" in result.stdout.lower()


def test_cli_status(runner, temp_db):
    from ebay_tracker.cli import app

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0


def test_cli_fetch_no_searches(runner, temp_db):
    from ebay_tracker.cli import app

    result = runner.invoke(app, ["fetch"])

    assert result.exit_code == 0
    assert "no searches" in result.stdout.lower()


def test_cli_fetch_specific_search_not_found(runner, temp_db):
    from ebay_tracker.cli import app

    result = runner.invoke(app, ["fetch", "Nonexistent"])

    assert result.exit_code == 1 or "not found" in result.stdout.lower()


def test_cli_analyze_no_data(runner, temp_db):
    from ebay_tracker.cli import app

    runner.invoke(app, ["add", "Test Search"])
    result = runner.invoke(app, ["analyze", "Test Search"])

    assert result.exit_code == 0
    assert "no data" in result.stdout.lower() or "0" in result.stdout


def test_cli_analyze_not_found(runner, temp_db):
    from ebay_tracker.cli import app

    result = runner.invoke(app, ["analyze", "Nonexistent"])

    assert result.exit_code == 1 or "not found" in result.stdout.lower()


def test_cli_history_not_found(runner, temp_db):
    from ebay_tracker.cli import app

    result = runner.invoke(app, ["history", "Nonexistent"])

    assert result.exit_code == 1 or "not found" in result.stdout.lower()


def test_cli_history_empty(runner, temp_db):
    from ebay_tracker.cli import app

    runner.invoke(app, ["add", "Test Search"])
    result = runner.invoke(app, ["history", "Test Search"])

    assert result.exit_code == 0


def test_cli_export_not_found(runner, temp_db):
    from ebay_tracker.cli import app

    result = runner.invoke(app, ["export", "Nonexistent"])

    assert result.exit_code == 1 or "not found" in result.stdout.lower()


def test_cli_add_with_new_filters(runner, temp_db):
    from ebay_tracker.cli import app

    result = runner.invoke(app, [
        "add", "Filtered Search",
        "--category", "11483",
        "--color", "Blue",
        "--size", "32",
        "--inseam", "30",
    ])

    assert result.exit_code == 0
    assert "Added" in result.stdout


def test_cli_edit_not_found(runner, temp_db):
    from ebay_tracker.cli import app

    result = runner.invoke(app, ["edit", "Nonexistent", "--color", "Blue"])

    assert result.exit_code == 1 or "not found" in result.stdout.lower()


def test_cli_edit_filters(runner, temp_db):
    from ebay_tracker.cli import app

    # Add a search first
    runner.invoke(app, ["add", "Test Search"])

    # Edit to add a filter
    result = runner.invoke(app, ["edit", "Test Search", "--color", "Blue"])

    assert result.exit_code == 0
    assert "Updated" in result.stdout
    assert "color" in result.stdout.lower()


def test_cli_edit_clear_filters(runner, temp_db):
    from ebay_tracker.cli import app

    # Add a search with filters
    runner.invoke(app, ["add", "Test Search", "--color", "Blue"])

    # Clear all filters
    result = runner.invoke(app, ["edit", "Test Search", "--clear-filters"])

    assert result.exit_code == 0
    assert "Cleared" in result.stdout


def test_cli_edit_no_changes(runner, temp_db):
    from ebay_tracker.cli import app

    # Add a search
    runner.invoke(app, ["add", "Test Search"])

    # Edit with no changes
    result = runner.invoke(app, ["edit", "Test Search"])

    assert result.exit_code == 0
    assert "No changes" in result.stdout
