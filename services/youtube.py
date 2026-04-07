import asyncio

import yt_dlp

YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
}

YTDL_PLAYLIST_OPTIONS = {
    'quiet': True,
    # extract_flat skips resolving individual video pages, returning only metadata
    'extract_flat': 'in_playlist',
    'noplaylist': False,
}

YTDL_METADATA_OPTIONS = {
    'quiet': True,
    'noplaylist': True,
    # extract_flat avoids opening individual video pages for search results,
    # making title lookups significantly faster for ytsearch: queries
    'extract_flat': True,
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

FETCH_TIMEOUT = 30


class YouTubeService:
    """Talks to YouTube via yt-dlp to pull streamable audio URLs."""

    @staticmethod
    def build_query(query: str) -> str:
        """
        Passes URLs through as-is; wraps plain text in a ytsearch: prefix.

        :param query: A raw YouTube URL or plain-text search string.
        :return: The original URL if it starts with 'http', otherwise a 'ytsearch:' prefixed string.
        """
        return query if query.startswith('http') else f'ytsearch:{query}'

    @staticmethod
    def is_playlist_url(query: str) -> bool:
        """
        Returns True if the query looks like a YouTube playlist URL.
        YouTube Mix/Radio playlists (list=RD…) are excluded because they are
        auto-generated and functionally infinite — treat those as single videos.

        :param query: The raw user input.
        :return: True when the URL contains a 'list=' parameter that is not a Mix/Radio list.
        """
        return query.startswith('http') and 'list=' in query and 'list=RD' not in query

    async def fetch_audio(self, query: str) -> tuple[str, str, str, str | None, str | None, int]:
        """
        Asks yt-dlp for the best audio stream for a query.
        Runs in a thread executor so it doesn't block the event loop.

        :param query: A YouTube URL or yt-dlp search string (e.g. 'ytsearch:lofi hip hop').
        :return: A tuple of (stream_url, title, webpage_url, thumbnail_url, uploader, duration_seconds).
        :raises asyncio.TimeoutError: When yt-dlp takes too long to respond.
        :raises yt_dlp.utils.DownloadError: When yt-dlp cannot find any results.
        """
        loop = asyncio.get_event_loop()
        with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
            info = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: ydl.extract_info(query, download = False)),
                timeout = FETCH_TIMEOUT,
            )
            # Search queries wrap their result in an 'entries' list; unwrap to get the first hit
            if 'entries' in info:
                info = info['entries'][0]
            uploader = info.get('uploader') or info.get('channel')
            return info['url'], info['title'], info['webpage_url'], info.get('thumbnail'), uploader, info.get('duration') or 0

    async def fetch_metadata(self, query: str) -> tuple[str, str]:
        """
        Fetches the title and webpage URL for a query without resolving the audio stream URL.
        For search queries this is faster than ``fetch_audio`` as yt-dlp uses ``extract_flat``
        and avoids visiting individual video pages.

        :param query: A YouTube URL or yt-dlp search string.
        :return: A tuple of (title, webpage_url).
        :raises asyncio.TimeoutError: When yt-dlp takes too long to respond.
        :raises yt_dlp.utils.DownloadError: When yt-dlp cannot find any results.
        """
        loop = asyncio.get_event_loop()
        with yt_dlp.YoutubeDL(YTDL_METADATA_OPTIONS) as ydl:
            info = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: ydl.extract_info(query, download = False)),
                timeout = FETCH_TIMEOUT,
            )
            if 'entries' in info:
                info = info['entries'][0]
            # extract_flat results may omit 'webpage_url', so fall back to constructing it from the video ID
            webpage_url = info.get('webpage_url') or f"https://www.youtube.com/watch?v={info['id']}"
            return info['title'], webpage_url

    async def fetch_playlist(self, url: str) -> list[tuple[str, str]]:
        """
        Extracts all video entries from a YouTube playlist URL without downloading audio.
        Runs in a thread executor so it doesn't block the event loop.

        :param url: A YouTube playlist or video-in-playlist URL.
        :return: A list of (webpage_url, title) tuples for each entry in the playlist.
        :raises asyncio.TimeoutError: When yt-dlp takes too long to respond.
        :raises yt_dlp.utils.DownloadError: When yt-dlp cannot access the playlist.
        """
        loop = asyncio.get_event_loop()
        with yt_dlp.YoutubeDL(YTDL_PLAYLIST_OPTIONS) as ydl:
            info = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: ydl.extract_info(url, download = False)),
                timeout = FETCH_TIMEOUT,
            )
            entries = info.get('entries') or []
            # Private or deleted videos come back as None entries, so we skip those
            return [
                (f"https://www.youtube.com/watch?v={entry['id']}", entry.get('title') or entry['id'])
                for entry in entries if entry and entry.get('id')
            ]
