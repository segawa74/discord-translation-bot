from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.translator import Translator


@pytest.mark.asyncio
async def test_translator_success():
    with patch("src.translator.genai.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_aio = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "こんにちは"
        mock_aio.models.generate_content = AsyncMock(return_value=mock_response)
        mock_client.aio = mock_aio
        mock_client_cls.return_value = mock_client

        translator = Translator(api_key="fake-key")
        result = await translator.translate("Hello", "ja")
        assert result == "こんにちは"
        mock_aio.models.generate_content.assert_awaited_once()


@pytest.mark.asyncio
async def test_translator_invalid_lang():
    translator = Translator(api_key="fake-key")
    result = await translator.translate("Hello", "invalid")
    assert result is None


@pytest.mark.asyncio
async def test_translator_api_error():
    with patch("src.translator.genai.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_aio = MagicMock()
        mock_aio.models.generate_content = AsyncMock(side_effect=Exception("API Error"))
        mock_client.aio = mock_aio
        mock_client_cls.return_value = mock_client

        translator = Translator(api_key="fake-key")
        result = await translator.translate("Hello", "ja")
        assert result is None
