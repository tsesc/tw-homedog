"""Tests for logging setup."""

import logging

import pytest

from tw_homedog.log import setup_logging, set_log_level


def test_setup_logging_default_level():
    setup_logging()
    root = logging.getLogger()
    assert root.level == logging.INFO


def test_setup_logging_custom_level():
    setup_logging(level="DEBUG")
    root = logging.getLogger()
    assert root.level == logging.DEBUG


def test_setup_logging_env_var(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    setup_logging()
    root = logging.getLogger()
    assert root.level == logging.WARNING


def test_setup_logging_explicit_overrides_env(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    setup_logging(level="DEBUG")
    root = logging.getLogger()
    assert root.level == logging.DEBUG


def test_setup_logging_with_file_handler(tmp_path):
    log_dir = str(tmp_path / "logs")
    setup_logging(log_dir=log_dir)
    root = logging.getLogger()
    handler_types = [type(h).__name__ for h in root.handlers]
    assert "RotatingFileHandler" in handler_types
    assert "StreamHandler" in handler_types


def test_setup_logging_creates_log_dir(tmp_path):
    log_dir = tmp_path / "nested" / "logs"
    setup_logging(log_dir=str(log_dir))
    assert log_dir.exists()


def test_set_log_level():
    setup_logging(level="INFO")
    set_log_level("DEBUG")
    root = logging.getLogger()
    assert root.level == logging.DEBUG
    for handler in root.handlers:
        assert handler.level == logging.DEBUG


def test_set_log_level_invalid():
    with pytest.raises(ValueError, match="Invalid log level"):
        set_log_level("NONSENSE")
