import asyncio

import discord
from discord.ext import commands

from services.spotify import SpotifyService
from services.youtube import FFMPEG_OPTIONS, YouTubeService


class MusicCog(commands.Cog):
    """Discord Cog providing music playback and queue management commands."""

    def __init__(self, bot: commands.Bot, youtube: YouTubeService, spotify: SpotifyService) -> None:
        """
        Initializes the MusicCog with the bot instance and required services.

        :param bot: The running Discord bot instance.
        :param youtube: The YouTubeService instance used for audio extraction.
        :param spotify: The SpotifyService instance used for track resolution.
        """
        self.bot = bot
        self.youtube = youtube
        self.spotify = spotify
        self._queues: dict[int, list[dict]] = {}
        self._loop: dict[int, bool] = {}
        self._current: dict[int, dict | None] = {}
        self._disconnect_tasks: dict[int, asyncio.Task] = {}

    def get_queue(self, guild_id: int) -> list[dict]:
        """
        Returns the song queue for a given guild, creating it if it does not exist.

        :param guild_id: The Discord guild (server) ID.
        :return: A list of queued song dicts, each with 'query' and 'title' keys.
        """
        if guild_id not in self._queues:
            self._queues[guild_id] = []
        return self._queues[guild_id]

    def is_looping(self, guild_id: int) -> bool:
        """
        Returns whether loop mode is enabled for a given guild.

        :param guild_id: The Discord guild (server) ID.
        :return: True if loop is enabled, False otherwise.
        """
        return self._loop.get(guild_id, False)

    def set_loop(self, guild_id: int, value: bool) -> None:
        """
        Sets the loop mode for a given guild.

        :param guild_id: The Discord guild (server) ID.
        :param value: True to enable looping, False to disable.
        """
        self._loop[guild_id] = value

    def get_current(self, guild_id: int) -> dict | None:
        """
        Returns the currently playing song for a given guild.

        :param guild_id: The Discord guild (server) ID.
        :return: A song dict with 'query' and 'title' keys, or None if nothing is playing.
        """
        return self._current.get(guild_id)

    def _cancel_disconnect(self, guild_id: int) -> None:
        """
        Cancels any pending inactivity disconnect task for a given guild.

        :param guild_id: The Discord guild (server) ID.
        """
        task = self._disconnect_tasks.pop(guild_id, None)
        if task:
            task.cancel()

    def _schedule_disconnect(self, ctx: commands.Context) -> None:
        """
        Schedules an automatic disconnect after 10 minutes of inactivity.
        Cancels any previously scheduled task for the guild before creating a new one.

        :param ctx: The command context used to access the voice client and send messages.
        """
        self._cancel_disconnect(ctx.guild.id)
        self._disconnect_tasks[ctx.guild.id] = asyncio.create_task(
            self._disconnect_after_timeout(ctx)
        )

    async def _disconnect_after_timeout(self, ctx: commands.Context) -> None:
        """
        Waits 10 minutes, then disconnects from the voice channel if nothing is playing.

        :param ctx: The command context used to access the voice client and send messages.
        """
        await asyncio.sleep(600)
        if ctx.voice_client and not ctx.voice_client.is_playing():
            self.get_queue(ctx.guild.id).clear()
            self.set_loop(ctx.guild.id, False)
            self._current.pop(ctx.guild.id, None)
            self._disconnect_tasks.pop(ctx.guild.id, None)
            await ctx.voice_client.disconnect()
            await ctx.send("Disconnected due to 10 minutes of inactivity.")

    async def _stream(self, ctx: commands.Context, query: str, title: str, webpage_url: str) -> None:
        """
        Creates an audio source and begins playback, chaining to the next song when done.
        Replays the current song instead of advancing if loop mode is enabled.

        :param ctx: The command context used to access the voice client and send messages.
        :param query: The yt-dlp compatible query string for the song.
        :param title: The display title of the song.
        :param webpage_url: The YouTube watch URL to display beneath the now-playing message.
        """
        self._cancel_disconnect(ctx.guild.id)
        audio_url, _, _ = await self.youtube.fetch_audio(query)
        source = discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(audio_url, **FFMPEG_OPTIONS), volume = 1.0
        )
        self._current[ctx.guild.id] = {"query": query, "title": title}

        def after_playing(error: Exception | None) -> None:
            if self.is_looping(ctx.guild.id):
                current = self.get_current(ctx.guild.id)
                if current:
                    asyncio.run_coroutine_threadsafe(
                        self._stream(ctx, current['query'], current['title'], webpage_url),
                        self.bot.loop,
                    )
            else:
                asyncio.run_coroutine_threadsafe(self._play_next(ctx), self.bot.loop)

        ctx.voice_client.play(source, after = after_playing)
        await ctx.send(f'Now playing: **{title}**\n{webpage_url}')

    async def _play_next(self, ctx: commands.Context) -> None:
        """
        Pops and plays the next song in the guild queue, if any.

        :param ctx: The command context used to access the voice client and send messages.
        """
        queue = self.get_queue(ctx.guild.id)
        if not ctx.voice_client:
            return
        if not queue:
            self._schedule_disconnect(ctx)
            return

        item = queue.pop(0)
        async with ctx.typing():
            _, title, webpage_url = await self.youtube.fetch_audio(item['query'])
            await self._stream(ctx, item['query'], title, webpage_url)

    async def _play_in_voice(self, ctx: commands.Context, query: str) -> None:
        """
        Joins the author's voice channel and streams audio from the given query.
        If audio is already playing, the song is added to the queue instead.

        :param ctx: The command context used to access voice state and send messages.
        :param query: A yt-dlp compatible query string (URL or 'ytsearch:...' prefix).
        """
        if not ctx.author.voice:
            await ctx.send("You must be in a voice channel.")
            return

        channel = ctx.author.voice.channel
        if ctx.voice_client is None:
            await channel.connect()
        elif ctx.voice_client.channel != channel:
            await ctx.voice_client.move_to(channel)

        async with ctx.typing():
            _, title, webpage_url = await self.youtube.fetch_audio(query)

            if ctx.voice_client.is_playing():
                self.get_queue(ctx.guild.id).append({"query": query, "title": title})
                await ctx.send(f'Added to queue: **{title}**')
                return

            ctx.voice_client.stop()
            await self._stream(ctx, query, title, webpage_url)

    @commands.command(name = 'y')
    async def youtube_cmd(self, ctx: commands.Context, *, query: str) -> None:
        """
        Plays audio from a YouTube URL or search query.
        Adds to the queue if something is already playing.

        :param ctx: The command context.
        :param query: A YouTube URL or plain-text search query.
        """
        await ctx.message.delete()
        await self._play_in_voice(ctx, self.youtube.build_query(query))

    @commands.command(name = 's')
    async def spotify_cmd(self, ctx: commands.Context, *, query: str) -> None:
        """
        Plays audio from a Spotify URL or search query by routing through YouTube.
        Adds to the queue if something is already playing.

        :param ctx: The command context.
        :param query: A Spotify track URL or plain-text search query.
        """
        await ctx.message.delete()
        search_query = self.spotify.resolve_query(query)
        if not search_query:
            await ctx.send("No results found on Spotify.")
            return
        await ctx.send(f'Found: **{search_query}** — searching YouTube...')
        await self._play_in_voice(ctx, f'ytsearch:{search_query}')

    @commands.command(name = 'add')
    async def add_cmd(self, ctx: commands.Context, *, query: str) -> None:
        """
        Adds a song to the queue without interrupting current playback.
        Accepts YouTube URLs/searches or Spotify URLs/searches.

        :param ctx: The command context.
        :param query: A YouTube/Spotify URL or plain-text search query.
        """
        await ctx.message.delete()

        if 'spotify.com/track/' in query:
            resolved = self.spotify.resolve_query(query)
            if not resolved:
                await ctx.send("No results found on Spotify.")
                return
            yt_query = f'ytsearch:{resolved}'
        else:
            yt_query = self.youtube.build_query(query)

        async with ctx.typing():
            _, title, _ = await self.youtube.fetch_audio(yt_query)
            self.get_queue(ctx.guild.id).append({"query": yt_query, "title": title})
            position = len(self.get_queue(ctx.guild.id))
            await ctx.send(f'Added to queue at position **{position}**: **{title}**')

    @commands.command(name = 'queue')
    async def queue_cmd(self, ctx: commands.Context) -> None:
        """
        Displays the current song queue.

        :param ctx: The command context.
        """
        await ctx.message.delete()
        queue = self.get_queue(ctx.guild.id)
        if not queue:
            await ctx.send("The queue is empty.")
            return
        lines = [f"`{i + 1}.` {item['title']}" for i, item in enumerate(queue)]
        await ctx.send("**Queue:**\n" + "\n".join(lines))

    @commands.command(name = 'remove')
    async def remove_cmd(self, ctx: commands.Context, index: int) -> None:
        """
        Removes a song from the queue by its 1-based position number.

        :param ctx: The command context.
        :param index: The 1-based position of the song to remove.
        """
        await ctx.message.delete()
        queue = self.get_queue(ctx.guild.id)
        if index < 1 or index > len(queue):
            await ctx.send(f"Invalid position. Queue has **{len(queue)}** item(s).")
            return
        removed = queue.pop(index - 1)
        await ctx.send(f'Removed: **{removed["title"]}**')

    @commands.command(name = 'skip')
    async def skip_cmd(self, ctx: commands.Context) -> None:
        """
        Skips the current song and plays the next one in the queue.

        :param ctx: The command context.
        """
        await ctx.message.delete()
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()  # triggers after_playing → _play_next
        else:
            await ctx.send("Nothing is playing.")

    @commands.command(name = 'loop')
    async def loop_cmd(self, ctx: commands.Context) -> None:
        """
        Toggles loop mode for the current song. When enabled, the current song
        replays indefinitely instead of advancing to the next item in the queue.

        :param ctx: The command context.
        """
        await ctx.message.delete()
        enabled = not self.is_looping(ctx.guild.id)
        self.set_loop(ctx.guild.id, enabled)
        state = "enabled" if enabled else "disabled"
        await ctx.send(f'Loop {state}.')

    @commands.command(name = 'pause')
    async def pause_cmd(self, ctx: commands.Context) -> None:
        """
        Pauses playback if currently playing, or resumes it if currently paused.

        :param ctx: The command context.
        """
        await ctx.message.delete()
        vc = ctx.voice_client
        if not vc:
            await ctx.send("Not connected to a voice channel.")
            return
        if vc.is_paused():
            vc.resume()
            await ctx.send("Resumed.")
        elif vc.is_playing():
            vc.pause()
            await ctx.send("Paused.")
        else:
            await ctx.send("Nothing is playing.")

    @commands.command(name = 'stop')
    async def stop_cmd(self, ctx: commands.Context) -> None:
        """
        Stops playback, clears the queue, and disconnects from the voice channel.

        :param ctx: The command context.
        """
        await ctx.message.delete()
        if ctx.voice_client:
            self.get_queue(ctx.guild.id).clear()
            self.set_loop(ctx.guild.id, False)
            self._current.pop(ctx.guild.id, None)
            self._cancel_disconnect(ctx.guild.id)
            ctx.voice_client.stop()
            await ctx.voice_client.disconnect()
