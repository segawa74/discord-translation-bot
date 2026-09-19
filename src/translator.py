from google import genai
from google.genai.errors import APIError

from src.config import LANG_SETTINGS, get_gemini_api_key


class Translator:
    def __init__(self, api_key: str | None = None):
        key = api_key or get_gemini_api_key()
        self.client = genai.Client(api_key=key)
        self.model_name = "gemini-3.1-flash-lite"

    async def translate(self, text: str, target_lang_code: str) -> str | None:
        """Translate text into natural casual spoken language using Gemini API."""
        if target_lang_code not in LANG_SETTINGS:
            return None

        target_name = LANG_SETTINGS[target_lang_code]["name"]
        prompt = f"""
You are a professional interpreter for a voice chat.
Translate the following text into natural, casual spoken {target_name}.
Do not add any explanations or notes. Just output the translated text.

Text: {text}
Translation:
"""

        try:
            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=prompt,
            )
            if response and response.text:
                return response.text.strip()
            return None
        except APIError as e:
            print(f"Gemini API Error: {e}")
            return None
        except Exception as e:
            print(f"Unexpected Translation Error: {e}")
            return None
