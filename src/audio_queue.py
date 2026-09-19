import asyncio
import os
import uuid

import discord
import edge_tts


class AudioQueueManager:
    def __init__(self):
        self.queues: dict[int, asyncio.Queue] = {}
        self.workers: dict[int, asyncio.Task] = {}

    def get_queue(self, guild_id: int) -> asyncio.Queue:
        if guild_id not in self.queues:
            self.queues[guild_id] = asyncio.Queue()
        return self.queues[guild_id]

    def ensure_worker(self, guild: discord.Guild, text_channel: discord.TextChannel):
        if guild.id not in self.workers or self.workers[guild.id].done():
            self.workers[guild.id] = asyncio.create_task(
                self._audio_worker(guild, text_channel)
            )

    async def add_item(
        self,
        guild: discord.Guild,
        text_channel: discord.TextChannel,
        text: str,
        voice_name: str,
    ):
        queue = self.get_queue(guild.id)
        await queue.put((text, voice_name))
        self.ensure_worker(guild, text_channel)

    async def _audio_worker(
        self, guild: discord.Guild, text_channel: discord.TextChannel
    ):
        queue = self.get_queue(guild.id)
        while True:
            try:
                try:
                    text, voice_name = await asyncio.wait_for(
                        queue.get(), timeout=300.0
                    )
                except asyncio.TimeoutError:
                    break

                if not guild.voice_client or not guild.voice_client.is_connected():
                    queue.task_done()
                    continue

                audio_filename = f"tts_{guild.id}_{uuid.uuid4()}.mp3"
                try:
                    communicate = edge_tts.Communicate(text, voice_name)
                    await communicate.save(audio_filename)
                except Exception as e:
                    print(f"Edge TTS Generation Error (Guild {guild.id}): {e}")
                    queue.task_done()
                    continue

                while guild.voice_client and guild.voice_client.is_playing():
                    await asyncio.sleep(0.3)

                if guild.voice_client and guild.voice_client.is_connected():
                    try:
                        source = discord.FFmpegPCMAudio(audio_filename)
                        guild.voice_client.play(source)

                        while guild.voice_client and guild.voice_client.is_playing():
                            await asyncio.sleep(0.3)
                    except Exception as e:
                        print(f"Audio Playback Error (Guild {guild.id}): {e}")

                if os.path.exists(audio_filename):
                    try:
                        os.remove(audio_filename)
                    except Exception as e:
                        print(f"Failed to remove temp file {audio_filename}: {e}")

                queue.task_done()
            except Exception as e:
                print(f"Audio Worker Error (Guild {guild.id}): {e}")
                await asyncio.sleep(1.0)

    async def cleanup_guild(self, guild_id: int):
        if guild_id in self.workers:
            self.workers[guild_id].cancel()
            del self.workers[guild_id]
        if guild_id in self.queues:
            del self.queues[guild_id]
