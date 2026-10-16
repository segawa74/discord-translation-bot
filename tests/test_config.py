import pytest

from src.config import LANG_SETTINGS, get_shutdown_timeout


def test_lang_settings():
    assert "ja" in LANG_SETTINGS
    assert "en" in LANG_SETTINGS
    assert "ko" in LANG_SETTINGS
    assert LANG_SETTINGS["ja"]["voice"] == "ja-JP-NanamiNeural"
    assert LANG_SETTINGS["en"]["voice"] == "en-US-AndrewNeural"
    assert LANG_SETTINGS["ko"]["voice"] == "ko-KR-SunHiNeural"


def test_shutdown_timeout_defaults_to_twenty_seconds(monkeypatch):
    monkeypatch.delenv("SHUTDOWN_TIMEOUT_SECONDS", raising=False)

    assert get_shutdown_timeout() == 20.0


def test_shutdown_timeout_reads_positive_environment_value(monkeypatch):
    monkeypatch.setenv("SHUTDOWN_TIMEOUT_SECONDS", "17.5")

    assert get_shutdown_timeout() == 17.5


@pytest.mark.parametrize("value", ["0", "-1", "nan", "invalid"])
def test_shutdown_timeout_rejects_invalid_values(monkeypatch, value):
    monkeypatch.setenv("SHUTDOWN_TIMEOUT_SECONDS", value)

    with pytest.raises(ValueError):
        get_shutdown_timeout()
