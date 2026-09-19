from src.config import LANG_SETTINGS


def test_lang_settings():
    assert "ja" in LANG_SETTINGS
    assert "en" in LANG_SETTINGS
    assert "ko" in LANG_SETTINGS
    assert LANG_SETTINGS["ja"]["voice"] == "ja-JP-NanamiNeural"
    assert LANG_SETTINGS["en"]["voice"] == "en-US-AndrewNeural"
    assert LANG_SETTINGS["ko"]["voice"] == "ko-KR-SunHiNeural"
