import discord

from src.audio_queue import AudioQueueManager
from src.config import LANG_SETTINGS
from src.translator import Translator


class TranslationBot:
    def __init__(self, token: str):
        self.token = token
        intents = discord.Intents.default()
        intents.message_content = True
        self.client = discord.Client(intents=intents)

        self.translator = Translator()
        self.audio_manager = AudioQueueManager()

        self.guild_settings: dict[int, dict] = {}

        self._register_events()

    def _register_events(self):
        @self.client.event
        async def on_ready():
            print(f"Logged in as {self.client.user}")

        @self.client.event
        async def on_message(message: discord.Message):
            if message.author.bot or not message.guild:
                return

            if message.content == "!join":
                if message.author.voice:
                    try:
                        voice_client = message.guild.voice_client
                        if voice_client and voice_client.is_connected():
                            await voice_client.move_to(message.author.voice.channel)
                        else:
                            await message.author.voice.channel.connect()

                        self.guild_settings[message.guild.id] = {
                            "channel_id": message.channel.id,
                            "lang": "ja",
                        }
                        await message.channel.send(
                            "Connected! Default: **Japanese**. "
                            "Use `!en`, `!ko`, `!ja` to switch."
                        )
                    except Exception as e:
                        print(f"Join VC Error: {e}")
                        await message.channel.send(
                            f"Failed to connect to Voice Channel: {e}"
                        )
                else:
                    await message.channel.send("Join VC first!")
                return

            if message.content == "!bye":
                if message.guild.voice_client:
                    try:
                        await message.guild.voice_client.disconnect()
                    except Exception as e:
                        print(f"Disconnect Error: {e}")

                if message.guild.id in self.guild_settings:
                    del self.guild_settings[message.guild.id]
                await self.audio_manager.cleanup_guild(message.guild.id)
                await message.channel.send("Disconnected.")
                return

            cmd = message.content.replace("!", "")
            if message.content.startswith("!") and cmd in LANG_SETTINGS:
                if message.guild.id in self.guild_settings:
                    self.guild_settings[message.guild.id]["lang"] = cmd
                    lang_name = LANG_SETTINGS[cmd]["name"]
                    await message.channel.send(f"Language switched to **{lang_name}**.")
                else:
                    await message.channel.send("Not connected. Use `!join` first.")
                return

            if message.guild.voice_client and message.guild.voice_client.is_connected():
                if not message.content or message.content.startswith("!"):
                    return

                settings = self.guild_settings.get(message.guild.id)
                if not settings:
                    return

                if message.channel.id != settings["channel_id"]:
                    return

                print(f"Received ({message.guild.name}): {message.content}")

                current_lang = settings["lang"]
                voice = LANG_SETTINGS[current_lang]["voice"]

                translated = await self.translator.translate(
                    message.content, current_lang
                )
                if not translated:
                    return

                print(f"Translated ({current_lang}): {translated}")
                try:
                    await message.channel.send(f"> {translated}")
                except Exception as e:
                    print(f"Failed to send message to channel: {e}")

                await self.audio_manager.add_item(
                    message.guild, message.channel, translated, voice
                )

    def run(self):
        self.client.run(self.token)
