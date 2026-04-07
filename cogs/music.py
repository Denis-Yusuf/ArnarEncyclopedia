import asyncio
import random

import discord
import yt_dlp
from discord.ext import commands

from services.spotify import SpotifyService
from services.youtube import FFMPEG_OPTIONS, YouTubeService


class NowPlayingView(discord.ui.View):
    """Buttons that sit under the now-playing message so you can control playback without typing commands."""

    def __init__(self, cog: 'MusicCog', ctx: commands.Context, duration: int = 0) -> None:
        """
        :param cog: Used to access and mutate playback state.
        :param ctx: Used to resolve the voice client and guild.
        :param duration: Song duration in seconds; if provided, a seek select is added.
        """
        super().__init__(timeout = None)
        self.cog = cog
        self.ctx = ctx
        if duration > 0:
            self.add_item(SeekSelect(cog, ctx, duration))

    def disable_all(self) -> None:
        """Greys out all buttons once there's nothing left to control."""
        for item in self.children:
            item.disabled = True

    @discord.ui.button(label = '⏸ Pause', style = discord.ButtonStyle.secondary)
    async def pause_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """
        Pauses or resumes depending on the current state. Label and colour flip to match.

        :param interaction: The interaction created by the button press.
        :param button: The button that was clicked.
        """
        vc = self.ctx.voice_client
        if not vc:
            await interaction.response.defer()
            return
        if vc.is_paused():
            vc.resume()
            button.label = '⏸ Pause'
            button.style = discord.ButtonStyle.secondary
        elif vc.is_playing():
            vc.pause()
            button.label = '▶ Resume'
            button.style = discord.ButtonStyle.success
        await interaction.response.edit_message(view = self)

    @discord.ui.button(label = '⏭ Skip', style = discord.ButtonStyle.primary)
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """
        Skips the current song. Stopping the VC triggers the after_playing chain into the next one.

        :param interaction: The interaction created by the button press.
        :param button: The button that was clicked.
        """
        vc = self.ctx.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()
        await interaction.response.defer()

    @discord.ui.button(label = '🔁 Loop', style = discord.ButtonStyle.secondary)
    async def loop_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """
        Toggles loop mode. Turns green so you can tell it's on at a glance.

        :param interaction: The interaction created by the button press.
        :param button: The button that was clicked.
        """
        enabled = not self.cog.is_looping(self.ctx.guild.id)
        self.cog.set_loop(self.ctx.guild.id, enabled)
        button.style = discord.ButtonStyle.success if enabled else discord.ButtonStyle.secondary
        await interaction.response.edit_message(view = self)

    @discord.ui.button(label = '⏹ Stop', style = discord.ButtonStyle.danger)
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """
        Kills playback, wipes the queue, and leaves the channel.

        :param interaction: The interaction created by the button press.
        :param button: The button that was clicked.
        """
        if self.ctx.voice_client:
            self.cog.get_queue(self.ctx.guild.id).clear()
            self.cog.set_loop(self.ctx.guild.id, False)
            self.cog._current.pop(self.ctx.guild.id, None)
            self.cog._seek_to.pop(self.ctx.guild.id, None)
            self.cog._cancel_disconnect(self.ctx.guild.id)
            self.ctx.voice_client.stop()
            await self.ctx.voice_client.disconnect()
        self.cog._now_playing_messages.pop(self.ctx.guild.id, None)
        self.cog._now_playing_views.pop(self.ctx.guild.id, None)
        self.disable_all()
        await interaction.response.edit_message(view = self)


class QueueSelect(discord.ui.Select):
    """Dropdown that lists the queue so you can jump straight to any song."""

    def __init__(self, cog: 'MusicCog', ctx: commands.Context, queue: list[dict]) -> None:
        """
        :param cog: Used to access and mutate queue state.
        :param ctx: Used to resolve the voice client and guild.
        :param queue: The current list of queued song dicts.
        """
        # Discord caps select menus at 25 options, so we just take the first 25
        self.cog = cog
        self.ctx = ctx
        options = [
            discord.SelectOption(label = f"{position + 1}. {item['title'][:90]}", value = str(position))
            for position, item in enumerate(queue[:25])
        ]
        super().__init__(placeholder = 'Skip to a song...', options = options)

    async def callback(self, interaction: discord.Interaction) -> None:
        """
        Drops everything before the chosen song and stops the current track so the next one kicks in.

        :param interaction: The interaction created by the select menu.
        """
        index = int(self.values[0])
        queue = self.cog.get_queue(self.ctx.guild.id)
        # Slice off everything before the chosen index so it becomes the next song up
        del queue[:index]
        vc = self.ctx.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()
        self.disabled = True
        await interaction.response.edit_message(view = self.view)


class QueueView(discord.ui.View):
    """Wraps QueueSelect into a view that gets attached to the /queue message."""

    def __init__(self, cog: 'MusicCog', ctx: commands.Context) -> None:
        """
        :param cog: Passed through to QueueSelect.
        :param ctx: Passed through to QueueSelect.
        """
        super().__init__(timeout = 60)
        queue = cog.get_queue(ctx.guild.id)
        if queue:
            self.add_item(QueueSelect(cog, ctx, queue))


class SeekSelect(discord.ui.Select):
    """Dropdown that lets you jump to an evenly-spaced timestamp in the current song."""

    def __init__(self, cog: 'MusicCog', ctx: commands.Context, duration: int) -> None:
        """
        :param cog: Used to set the seek target and stop the voice client.
        :param ctx: Used to resolve the voice client and guild.
        :param duration: Total song duration in seconds, used to generate timestamp options.
        """
        self.cog = cog
        self.ctx = ctx
        # Aim for up to 24 evenly spaced options; minimum interval is 15 seconds
        count = min(24, max(1, duration // 15))
        interval = duration // count
        options = [
            discord.SelectOption(
                label = f"{(i * interval) // 60}:{(i * interval) % 60:02d}",
                value = str(i * interval),
            )
            for i in range(count)
        ]
        super().__init__(placeholder = 'Seek to...', options = options, row = 1)

    async def callback(self, interaction: discord.Interaction) -> None:
        """
        Sets the seek target on the cog then stops the voice client.
        ``_stream`` picks up ``_seek_to`` after ``done.wait()`` and restarts from that offset.

        :param interaction: The interaction created by the select menu.
        """
        vc = self.ctx.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            self.cog._seek_to[self.ctx.guild.id] = int(self.values[0])
            vc.stop()
        await interaction.response.defer()


class MusicCog(commands.Cog):
    """Handles all music commands and keeps per-guild playback state."""

    def __init__(self, bot: commands.Bot, youtube: YouTubeService, spotify: SpotifyService) -> None:
        """
        :param bot: The running Discord bot instance.
        :param youtube: Used for audio extraction.
        :param spotify: Used for track resolution.
        """
        self.bot = bot
        self.youtube = youtube
        self.spotify = spotify
        # All state is keyed by guild ID so the bot works across multiple servers
        self._queues: dict[int, list[dict]] = {}
        self._loop: dict[int, bool] = {}
        self._current: dict[int, dict | None] = {}
        self._disconnect_tasks: dict[int, asyncio.Task] = {}
        self._now_playing_messages: dict[int, discord.Message] = {}
        self._now_playing_views: dict[int, NowPlayingView] = {}
        self._seek_to: dict[int, int] = {}

    def get_queue(self, guild_id: int) -> list[dict]:
        """
        Returns the queue for a guild, creating an empty one on first access.

        :param guild_id: The Discord guild ID.
        :return: List of queued song dicts, each with 'query' and 'title' keys.
        """
        if guild_id not in self._queues:
            self._queues[guild_id] = []
        return self._queues[guild_id]

    def is_looping(self, guild_id: int) -> bool:
        """
        :param guild_id: The Discord guild ID.
        :return: True if loop mode is on for this guild.
        """
        return self._loop.get(guild_id, False)

    def set_loop(self, guild_id: int, value: bool) -> None:
        """
        :param guild_id: The Discord guild ID.
        :param value: True to enable looping, False to disable.
        """
        self._loop[guild_id] = value

    def get_current(self, guild_id: int) -> dict | None:
        """
        :param guild_id: The Discord guild ID.
        :return: The song currently playing, or None if nothing is.
        """
        return self._current.get(guild_id)

    def _is_queued(self, guild_id: int, title: str) -> bool:
        """
        Checks whether this title is already playing or sitting in the queue.

        :param guild_id: The Discord guild ID.
        :param title: The resolved display title to check for.
        :return: True if the title appears in the queue or is the current song.
        """
        if any(item['title'] == title for item in self.get_queue(guild_id)):
            return True
        current = self.get_current(guild_id)
        return current is not None and current['title'] == title

    def _cancel_disconnect(self, guild_id: int) -> None:
        """
        Cancels any pending inactivity disconnect for this guild.

        :param guild_id: The Discord guild ID.
        """
        task = self._disconnect_tasks.pop(guild_id, None)
        if task:
            task.cancel()

    def _schedule_disconnect(self, ctx: commands.Context) -> None:
        """
        Queues up an auto-disconnect after 5 minutes of silence, replacing any existing timer.

        :param ctx: Used to access the voice client and send messages.
        """
        self._cancel_disconnect(ctx.guild.id)
        self._disconnect_tasks[ctx.guild.id] = asyncio.create_task(
            self._disconnect_after_timeout(ctx)
        )

    async def _disconnect_after_timeout(self, ctx: commands.Context) -> None:
        """
        Waits 5 minutes and leaves the channel if nothing started playing in that time.

        :param ctx: Used to access the voice client and send messages.
        """
        time = 300
        await asyncio.sleep(time)
        if ctx.voice_client and not ctx.voice_client.is_playing():
            self.get_queue(ctx.guild.id).clear()
            self.set_loop(ctx.guild.id, False)
            self._current.pop(ctx.guild.id, None)
            self._disconnect_tasks.pop(ctx.guild.id, None)
            await self._clear_now_playing(ctx.guild.id)
            await ctx.voice_client.disconnect()
            await ctx.send("Disconnected due to {} minutes of inactivity.".format(round(time / 60)))

    async def _clear_now_playing(self, guild_id: int) -> None:
        """
        Disables the buttons on the last now-playing message and forgets about it.

        :param guild_id: The Discord guild ID.
        """
        view = self._now_playing_views.pop(guild_id, None)
        msg = self._now_playing_messages.pop(guild_id, None)
        if view and msg:
            view.disable_all()
            try:
                await msg.edit(view = view)
            except discord.NotFound:
                # Message was already deleted, nothing to update
                pass

    async def _stream(self, ctx: commands.Context, query: str, title: str, webpage_url: str, seek_offset: int = 0) -> None:
        """
        Fetches the audio stream URL, starts playback, and posts the now-playing message.
        Blocks until the track finishes, then either seeks, loops, or advances the queue.

        :param ctx: Used to access the voice client and send messages.
        :param query: yt-dlp compatible query string for the song.
        :param title: Display title of the song.
        :param webpage_url: YouTube watch URL shown under the now-playing message.
        :param seek_offset: Number of seconds to seek into the track before starting playback.
        """
        self._cancel_disconnect(ctx.guild.id)
        await self._clear_now_playing(ctx.guild.id)

        audio_url, _, _, thumbnail, uploader, duration = await self.youtube.fetch_audio(query)

        # Prepend -ss to before_options when seeking; a copy avoids mutating the module-level constant
        if seek_offset:
            ffmpeg_opts = {**FFMPEG_OPTIONS, 'before_options': f'-ss {seek_offset} ' + FFMPEG_OPTIONS['before_options']}
        else:
            ffmpeg_opts = FFMPEG_OPTIONS

        source = discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(audio_url, **ffmpeg_opts), volume = 0.5
        )
        self._current[ctx.guild.id] = {"query": query, "title": title, "duration": duration}
        view = NowPlayingView(self, ctx, duration)

        # asyncio.Event lets us await the end of playback without polling.
        # The after callback runs in a non-async thread, so we just set the event
        # there and await it here in the coroutine.
        done = asyncio.Event()
        ctx.voice_client.play(source, after = lambda error: done.set())

        embed = discord.Embed(
            title = title,
            url = webpage_url,
            color = 0xFF0000,
        )
        embed.set_author(
            name = uploader or 'Unknown',
            icon_url = 'https://www.youtube.com/s/desktop/28b0985e/img/favicon_32x32.png'
        )
        if thumbnail:
            embed.set_image(url = thumbnail)
        msg = await ctx.send(content = f'Now playing: **{title}**\n{webpage_url}', embed = embed, view = view)
        self._now_playing_messages[ctx.guild.id] = msg
        self._now_playing_views[ctx.guild.id] = view

        await done.wait()

        seek = self._seek_to.pop(ctx.guild.id, None)
        if seek is not None and ctx.voice_client:
            await self._stream(ctx, query, title, webpage_url, seek_offset = seek)
        elif self.is_looping(ctx.guild.id):
            current = self.get_current(ctx.guild.id)
            if current:
                await self._stream(ctx, current['query'], current['title'], webpage_url)
        else:
            await self._play_next(ctx)

    async def _play_next(self, ctx: commands.Context) -> None:
        """
        Pulls the next song off the queue and plays it, or starts the idle timer if the queue is empty.
        On fetch failure the failed item is skipped and this method calls itself recursively.

        :param ctx: Used to access the voice client and send messages.
        """
        queue = self.get_queue(ctx.guild.id)
        if not ctx.voice_client:
            return
        if not queue:
            await self._clear_now_playing(ctx.guild.id)
            self._schedule_disconnect(ctx)
            return

        item = queue.pop(0)
        async with ctx.typing():
            try:
                _, title, webpage_url, _, _, _ = await self.youtube.fetch_audio(item['query'])
            except asyncio.TimeoutError:
                await ctx.send(f"Timed out fetching **{item['title']}**, skipping.")
                # Recurse so the next item is attempted rather than leaving the queue stalled
                await self._play_next(ctx)
                return
            except yt_dlp.utils.DownloadError:
                await ctx.send(f"Could not load **{item['title']}**, skipping.")
                await self._play_next(ctx)
                return
            await self._stream(ctx, item['query'], title, webpage_url)

    async def _play_in_voice(self, ctx: commands.Context, query: str) -> None:
        """
        Joins the user's voice channel and plays the given query.
        If something is already playing, the song gets queued instead.

        :param ctx: Used to access voice state and send messages.
        :param query: yt-dlp compatible query string (URL or 'ytsearch:...' prefix).
        """
        if not ctx.author.voice:
            await ctx.send("You must be in a voice channel.")
            return

        channel = ctx.author.voice.channel
        if ctx.voice_client is None:
            await channel.connect(self_deaf = True)
        elif ctx.voice_client.channel != channel:
            await ctx.voice_client.move_to(channel)

        async with ctx.typing():
            try:
                _, title, webpage_url, _, _, _ = await self.youtube.fetch_audio(query)
            except asyncio.TimeoutError:
                await ctx.send("Search timed out. Try again or use a direct URL.")
                return
            except yt_dlp.utils.DownloadError:
                await ctx.send("No results found for that query.")
                return

            if ctx.voice_client.is_playing():
                if self._is_queued(ctx.guild.id, title):
                    await ctx.send(f'**{title}** is already in the queue.')
                    return
                self.get_queue(ctx.guild.id).append({"query": query, "title": title})
                await ctx.send(f'Added to queue: **{title}**')
                return

            ctx.voice_client.stop()
            await self._stream(ctx, query, title, webpage_url)

    async def _enqueue_playlist(self, ctx: commands.Context, url: str) -> None:
        """
        Fetches all entries from a YouTube playlist URL, bulk-adds them to the queue,
        and kicks off playback if nothing is currently playing.

        :param ctx: Used to access voice state and send messages.
        :param url: A YouTube playlist or video-in-playlist URL.
        """
        if not ctx.author.voice:
            await ctx.send("You must be in a voice channel.")
            return

        channel = ctx.author.voice.channel
        if ctx.voice_client is None:
            await channel.connect(self_deaf = True)
        elif ctx.voice_client.channel != channel:
            await ctx.voice_client.move_to(channel)

        async with ctx.typing():
            try:
                entries = await self.youtube.fetch_playlist(url)
            except asyncio.TimeoutError:
                await ctx.send("Playlist fetch timed out. Try again.")
                return
            except yt_dlp.utils.DownloadError:
                await ctx.send("Could not load that playlist.")
                return

            if not entries:
                await ctx.send("The playlist appears to be empty or unavailable.")
                return

            queue = self.get_queue(ctx.guild.id)
            added = 0
            # Track the first newly added entry so we can pop and play it immediately
            # if nothing is currently running, without replaying something mid-queue.
            first_entry = None
            for webpage_url, title in entries:
                if not self._is_queued(ctx.guild.id, title):
                    queue.append({"query": webpage_url, "title": title})
                    added += 1
                    if first_entry is None:
                        first_entry = queue[-1]

            await ctx.send(f'Added **{added}** song(s) from playlist to queue.')

            if not ctx.voice_client.is_playing() and first_entry:
                # Pop the first entry out of the queue and stream it directly,
                # so it doesn't get played twice if _play_next is also called
                item = queue.pop(queue.index(first_entry))
                try:
                    _, title, webpage_url, _, _, _ = await self.youtube.fetch_audio(item['query'])
                except (asyncio.TimeoutError, yt_dlp.utils.DownloadError):
                    await ctx.send(f"Could not load **{item['title']}**, skipping to next.")
                    await self._play_next(ctx)
                    return
                await self._stream(ctx, item['query'], title, webpage_url)

    @commands.hybrid_command(name = 'play', description = 'Play from a YouTube URL, playlist, Spotify URL, or search query.')
    async def play_cmd(self, ctx: commands.Context, *, query: str) -> None:
        """
        Universal play command. Routing priority:
        1. YouTube playlist URL (contains 'list=') → _enqueue_playlist
        2. Spotify track URL (contains 'spotify.com') → resolve via Spotify, then search YouTube
        3. Everything else → YouTube URL or search via _play_in_voice

        :param ctx: The invocation context.
        :param query: A YouTube URL, playlist URL, Spotify track URL, or plain-text search string.
        """
        if ctx.interaction is None:
            await ctx.message.delete()
        if self.youtube.is_playlist_url(query):
            await self._enqueue_playlist(ctx, query)
        elif 'spotify.com' in query:
            search_query = self.spotify.resolve_query(query)
            if not search_query:
                await ctx.send("No results found on Spotify.")
                return
            await ctx.send(f'Found: **{search_query}** — searching YouTube...')
            await self._play_in_voice(ctx, f'ytsearch:{search_query}')
        else:
            await self._play_in_voice(ctx, self.youtube.build_query(query))

    @commands.hybrid_command(name = 'add', description = 'Add a song or playlist to the queue without interrupting playback.')
    async def add_cmd(self, ctx: commands.Context, *, query: str) -> None:
        """
        Adds a song or playlist to the queue without interrupting whatever is currently playing.
        Accepts YouTube URLs, playlist URLs, Spotify track URLs, and plain-text search queries.

        :param ctx: The invocation context.
        :param query: A YouTube URL, playlist URL, Spotify track URL, or search string.
        """
        if ctx.interaction is None:
            await ctx.message.delete()

        if self.youtube.is_playlist_url(query):
            async with ctx.typing():
                try:
                    entries = await self.youtube.fetch_playlist(query)
                except asyncio.TimeoutError:
                    await ctx.send("Playlist fetch timed out. Try again.")
                    return
                except yt_dlp.utils.DownloadError:
                    await ctx.send("Could not load that playlist.")
                    return

                if not entries:
                    await ctx.send("The playlist appears to be empty or unavailable.")
                    return

                queue = self.get_queue(ctx.guild.id)
                # list.append always returns None, so `not queue.append(...)` is always True.
                # This lets us filter and append in a single pass without a separate loop.
                added = sum(
                    1 for webpage_url, title in entries
                    if not self._is_queued(ctx.guild.id, title)
                    and not queue.append({"query": webpage_url, "title": title})
                )
                await ctx.send(f'Added **{added}** song(s) from playlist to queue.')
            return

        if 'spotify.com/track/' in query:
            resolved = self.spotify.resolve_query(query)
            if not resolved:
                await ctx.send("No results found on Spotify.")
                return
            yt_query = f'ytsearch:{resolved}'
        else:
            yt_query = self.youtube.build_query(query)

        async with ctx.typing():
            try:
                title, _ = await self.youtube.fetch_metadata(yt_query)
            except asyncio.TimeoutError:
                await ctx.send("Search timed out. Try again or use a direct URL.")
                return
            except yt_dlp.utils.DownloadError:
                await ctx.send("No results found for that query.")
                return
            if self._is_queued(ctx.guild.id, title):
                await ctx.send(f'**{title}** is already in the queue.')
                return
            self.get_queue(ctx.guild.id).append({"query": yt_query, "title": title})
            position = len(self.get_queue(ctx.guild.id))
            await ctx.send(f'Added to queue at position **{position}**: **{title}**')

    @commands.hybrid_command(name = 'queue', description = 'Show the queue. Use the dropdown to skip to a song.')
    async def queue_cmd(self, ctx: commands.Context) -> None:
        """
        Displays the current queue with numbered entries and an interactive dropdown
        that lets you jump directly to any of the first 25 songs.

        :param ctx: The invocation context.
        """
        if ctx.interaction is None:
            await ctx.message.delete()
        queue = self.get_queue(ctx.guild.id)
        if not queue:
            await ctx.send("The queue is empty.")
            return
        lines = [f"`{position + 1}.` {item['title']}" for position, item in enumerate(queue)]
        suffix = f"\n*Showing first 25 of {len(queue)} songs.*" if len(queue) > 25 else ""
        await ctx.send("**Queue:**\n" + "\n".join(lines) + suffix, view = QueueView(self, ctx))

    @commands.hybrid_command(name = 'shuffle', description = 'Shuffle the song queue.')
    async def shuffle_cmd(self, ctx: commands.Context) -> None:
        """
        Randomly reorders all songs currently in the queue.
        Requires at least two songs to be present.

        :param ctx: The invocation context.
        """
        if ctx.interaction is None:
            await ctx.message.delete()
        queue = self.get_queue(ctx.guild.id)
        if len(queue) < 2:
            await ctx.send("Not enough songs in the queue to shuffle.")
            return
        random.shuffle(queue)
        await ctx.send("Queue shuffled.")

    @commands.hybrid_command(name = 'remove', description = 'Remove a song from the queue by its position number.')
    async def remove_cmd(self, ctx: commands.Context, index: int) -> None:
        """
        Removes the song at the given 1-based position from the queue.

        :param ctx: The invocation context.
        :param index: The 1-based position of the song to remove.
        """
        if ctx.interaction is None:
            await ctx.message.delete()
        queue = self.get_queue(ctx.guild.id)
        if index < 1 or index > len(queue):
            await ctx.send(f"Invalid position. Queue has **{len(queue)}** item(s).")
            return
        removed = queue.pop(index - 1)
        await ctx.send(f'Removed: **{removed["title"]}**')

    @commands.hybrid_command(name = 'skip', description = 'Skip the current song.')
    async def skip_cmd(self, ctx: commands.Context) -> None:
        """
        Stops the current track. The after-playback chain picks up the next song automatically.

        :param ctx: The invocation context.
        """
        if ctx.interaction is None:
            await ctx.message.delete()
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            await ctx.send("Skipped.")
        else:
            await ctx.send("Nothing is playing.")

    @commands.hybrid_command(name = 'loop', description = 'Toggle loop mode for the current song.')
    async def loop_cmd(self, ctx: commands.Context) -> None:
        """
        Toggles loop mode on or off. When on, the current song repeats indefinitely
        until loop is disabled or the song is skipped.

        :param ctx: The invocation context.
        """
        if ctx.interaction is None:
            await ctx.message.delete()
        enabled = not self.is_looping(ctx.guild.id)
        self.set_loop(ctx.guild.id, enabled)
        state = "enabled" if enabled else "disabled"
        await ctx.send(f'Loop {state}.')

    @commands.hybrid_command(name = 'pause', description = 'Toggle pause/resume.')
    async def pause_cmd(self, ctx: commands.Context) -> None:
        """
        Pauses playback if something is playing, or resumes if it is already paused.

        :param ctx: The invocation context.
        """
        if ctx.interaction is None:
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

    @commands.hybrid_command(name = 'stop', description = 'Stop playback, clear the queue, and disconnect.')
    async def stop_cmd(self, ctx: commands.Context) -> None:
        """
        Stops playback, clears the queue, cancels the inactivity timer, and disconnects from voice.

        :param ctx: The invocation context.
        """
        if ctx.interaction is None:
            await ctx.message.delete()
        if ctx.voice_client:
            self.get_queue(ctx.guild.id).clear()
            self.set_loop(ctx.guild.id, False)
            self._current.pop(ctx.guild.id, None)
            self._seek_to.pop(ctx.guild.id, None)
            self._cancel_disconnect(ctx.guild.id)
            await self._clear_now_playing(ctx.guild.id)
            ctx.voice_client.stop()
            await ctx.voice_client.disconnect()
            await ctx.send("Stopped.")
        else:
            await ctx.send("Not connected to a voice channel.")
